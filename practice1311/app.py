from contextlib import closing
import sqlite3

from flask import Flask, jsonify, redirect, render_template, request, url_for
from werkzeug.utils import secure_filename


app = Flask(
    __name__,
    template_folder=".",
    static_folder="textures",
    static_url_path="/texture-files",
)
app.config["DATABASE"] = app.root_path + "/app.db"
ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "gif"}


def get_db_connection():
    connection = sqlite3.connect(app.config["DATABASE"])
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    connection = sqlite3.connect(app.config["DATABASE"])
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS textures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            image TEXT NOT NULL
        )
        """
    )
    connection.commit()
    connection.close()


def validate_texture_form(require_image):
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    image = request.files.get("image")
    filename = secure_filename(image.filename) if image and image.filename else ""
    errors = []

    if not title:
        errors.append("Title is required")
    if not description:
        errors.append("Description is required")
    if require_image and not filename:
        errors.append("Texture image is required")
    if filename:
        extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if extension not in ALLOWED_IMAGE_EXTENSIONS:
            errors.append("Use a JPG, PNG, WEBP, or GIF image")

    return title, description, image if filename else None, filename, errors


def save_uploaded_image(image, original_filename, texture_id):
    extension = original_filename.rsplit(".", 1)[-1].lower()
    filename = f"texture_{texture_id}.{extension}"
    image.save(app.static_folder + "/" + filename)
    return filename


def render_database_error():
    app.logger.exception("A database operation failed")
    return jsonify({"error": "A database operation failed"}), 500


@app.route("/")
def index():
    search = request.args.get("q", "").strip()
    try:
        with closing(get_db_connection()) as connection:
            textures = connection.execute(
                """
                SELECT id, title, description, image
                FROM textures
                WHERE title LIKE ?
                ORDER BY id DESC
                """,
                (f"%{search}%",),
            ).fetchall()
    except sqlite3.Error:
        return render_database_error()

    return render_template("index.html", textures=textures, search=search)


@app.route("/textures/<int:texture_id>")
def detail(texture_id):
    try:
        with closing(get_db_connection()) as connection:
            texture = connection.execute(
                "SELECT id, title, description, image FROM textures WHERE id = ?",
                (texture_id,),
            ).fetchone()
    except sqlite3.Error:
        return render_database_error()

    if texture is None:
        return "Texture not found", 404
    return render_template("detail.html", texture=texture)


@app.route("/textures/add", methods=["GET", "POST"])
def add_texture():
    if request.method == "POST":
        title, description, image, original_filename, errors = validate_texture_form(
            require_image=True
        )
        if errors:
            return render_template(
                "add.html",
                errors=errors,
                title=title,
                description=description,
            )

        try:
            with closing(get_db_connection()) as connection:
                with connection:
                    result = connection.execute(
                        """
                        INSERT INTO textures (title, description, image)
                        VALUES (?, ?, '')
                        """,
                        (title, description),
                    )
                    texture_id = result.lastrowid
                    filename = save_uploaded_image(image, original_filename, texture_id)
                    connection.execute(
                        "UPDATE textures SET image = ? WHERE id = ?",
                        (filename, texture_id),
                    )
        except OSError:
            app.logger.exception("Could not save uploaded texture image")
            return jsonify({"error": "Could not save uploaded texture image"}), 500
        except sqlite3.Error:
            return render_database_error()

        return redirect(url_for("index"))

    return render_template("add.html")


@app.route("/textures/<int:texture_id>/edit", methods=["PUT"])
def edit_texture(texture_id):
    try:
        with closing(get_db_connection()) as connection:
            texture = connection.execute(
                "SELECT id, title, description, image FROM textures WHERE id = ?",
                (texture_id,),
            ).fetchone()
    except sqlite3.Error:
        return render_database_error()

    if texture is None:
        return jsonify({"error": "Texture not found"}), 404

    title, description, image, original_filename, errors = validate_texture_form(
        require_image=False
    )
    if errors:
        return jsonify({"errors": errors}), 400

    filename = texture["image"]
    try:
        if image:
            filename = save_uploaded_image(image, original_filename, texture_id)
        with closing(get_db_connection()) as connection:
            with connection:
                result = connection.execute(
                    """
                    UPDATE textures
                    SET title = ?, description = ?, image = ?
                    WHERE id = ?
                    """,
                    (title, description, filename, texture_id),
                )
    except OSError:
        app.logger.exception("Could not save uploaded texture image")
        return jsonify({"error": "Could not save uploaded texture image"}), 500
    except sqlite3.Error:
        return render_database_error()

    if result.rowcount == 0:
        return jsonify({"error": "Texture not found"}), 404

    return jsonify({"message": "Texture updated", "id": texture_id})


@app.route("/textures/<int:texture_id>/delete", methods=["DELETE"])
def delete_texture(texture_id):
    try:
        with closing(get_db_connection()) as connection:
            with connection:
                result = connection.execute(
                    "DELETE FROM textures WHERE id = ?", (texture_id,)
                )
    except sqlite3.Error:
        return render_database_error()

    if result.rowcount == 0:
        return jsonify({"error": "Texture not found"}), 404
    return jsonify({"message": "Texture deleted", "id": texture_id})


init_db()


if __name__ == "__main__":
    app.run(debug=True)
