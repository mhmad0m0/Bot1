from flask import Blueprint, render_template, request, abort, url_for, redirect
from sqlalchemy import or_
import os

# Import db from extensions, no need to import flask_app here for app_context
from ..extensions import db
from ..models.mod import Mod
from ..models.category import Category

main_routes = Blueprint("main_routes", __name__)

@main_routes.route("/")
def index():
    # Flask handles app context automatically in request handlers
    latest_mods = Mod.query.filter_by(status="approved").order_by(Mod.created_at.desc()).limit(10).all()
    categories = Category.query.order_by(Category.name).all()
    return render_template("index.html", latest_mods=latest_mods, categories=categories)

@main_routes.route("/mod/<int:mod_id>")
def mod_detail(mod_id):
    mod = Mod.query.filter_by(id=mod_id, status="approved").first_or_404()
    return render_template("mod_detail.html", mod=mod)

@main_routes.route("/category/<int:category_id>")
def category_mods(category_id):
    category = Category.query.get_or_404(category_id)
    mods_in_category = Mod.query.filter_by(category_id=category.id, status="approved").order_by(Mod.name).all()
    return render_template("category_mods.html", category=category, mods=mods_in_category)

@main_routes.route("/search")
def search():
    query = request.args.get("query", "")
    results = []
    if query:
        search_term = f"%{query}%"
        results = Mod.query.filter(
            Mod.name.ilike(search_term),
            Mod.status == "approved"
        ).order_by(Mod.name).all()
    return render_template("search_results.html", query=query, results=results)

@main_routes.route("/ping")
def ping():
    return "Pong! The website is running."

