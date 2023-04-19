from flask import Blueprint, render_template, url_for, request, redirect, flash
from app import webapp
import requests
from flask_bootstrap import Bootstrap
bootstrap = Bootstrap(webapp)
main = Blueprint('main', __name__, static_folder="static",
                 template_folder="template")


@main.route('/', methods=['GET'])
def landing():
    return render_template("home.html")


@main.route('/list_keys', methods=['GET'])
def home():
    url = "http://" + request.host + url_for("api.list_keys")
    response = requests.post(url)
    if response is None:
        flash('No response from server', 'error')
        return render_template("home.html")
    data = response.json()
    if data["success"] == "false":
        flash('Unknown error: get all keys failed', 'error')
        return render_template("home.html")
    keys = data["keys"]
    return render_template("list_keys.html", keys=keys)


@main.route('/search', methods=['GET', 'POST'])
def search():
    if request.method == 'GET':
        return render_template("search.html")
    elif request.method == "POST":
        key = request.form.get('key')
        if not key:
            flash('Please do not enter empty value', 'error')
            return render_template("search.html")
        url = "http://" + request.host + url_for("api.get", key_value=key)
        response = requests.post(url)
        if response is None:
            flash('No response from server', 'error')
            return render_template("search.html")
        data = response.json()
        if data["success"] == "false":
            flash(data['error']['message'], 'error')
            return render_template("search.html")
        image = data["content"]
        return render_template("display_image.html", image=image)


@main.route('/upload', methods=['GET', 'POST'])
def upload():
    if request.method == 'GET':
        return render_template("upload.html")
    elif request.method == "POST":
        key = request.form.get('key')
        file = request.files.get('file')
        if key and file:
            url = "http://" + request.host + url_for("api.put")
            files = {'file': (file.filename, file.stream, file.mimetype)}
            params = {'key': key}
            response = requests.post(url, data=params, files=files)
            if response is None:
                flash('No response from server', 'error')
                return render_template("upload.html")
            data = response.json()
            if data["success"] == "true":
                flash("Upload image successfully", 'success')
            else:
                flash("Upload image failed", 'error')
        else:
            flash("Missing key or file", 'error')
        return render_template("upload.html")
