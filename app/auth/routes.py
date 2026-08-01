from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash

from app.auth import auth_bp
from app.extensions import db
from app.models import User
from app.utils import (
    is_valid_email,
    is_valid_password,
)


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        name = request.form.get("name")

        if not is_valid_email(email):
            flash(
                "Please enter a valid email address.",
                "danger",
            )
            return redirect(url_for("auth.register"))

        if not is_valid_password(password):
            flash(
                "Password must be at least 8 characters long, include an uppercase letter, a digit, and a special character.",
                "danger",
            )
            return redirect(url_for("auth.register"))

        result = db.session.execute(db.select(User).where(User.email == email))
        user = result.scalar()
        if user:
            flash("You've already signed up with that email, log in instead!", "danger")
            return redirect(url_for("auth.login"))

        hash_and_salted_password = generate_password_hash(password, method="pbkdf2:sha256", salt_length=8)
        new_user = User(email=email, password=hash_and_salted_password, name=name)

        db.session.add(new_user)
        db.session.commit()
        login_user(new_user)
        if email == "adminadmin@gmail.com":
            return redirect(url_for("master.cliques"))
        return redirect(url_for("map.maptest"))

    return render_template("auth/register.html", logged_in=current_user.is_authenticated)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        result = db.session.execute(db.select(User).where(User.email == email))
        user = result.scalar()
        if not user:
            flash("That email does not exist, please try again.", "danger")
            return redirect(url_for("auth.login"))
        elif not check_password_hash(user.password, password):
            flash("Password incorrect, please try again.", "danger")
            return redirect(url_for("auth.login"))
        else:
            login_user(user)
            if user.email == "adminadmin@gmail.com":
                return redirect(url_for("master.cliques"))
            return redirect(url_for("map.maptest"))

    return render_template("auth/login.html", logged_in=current_user.is_authenticated)


@auth_bp.route("/logout")
@login_required
def logout():
    db.session.close()
    logout_user()
    return redirect(url_for("main.home"))
