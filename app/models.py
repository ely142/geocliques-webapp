from datetime import datetime

from flask_login import UserMixin
from sqlalchemy import Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db, login_manager


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(100), unique=True)
    password: Mapped[str] = mapped_column(String(100))
    picture: Mapped[str] = mapped_column(String(150), default="default.jpg")

    cliques = relationship("CliqueUser", back_populates="user")
    markers = relationship("UserMarker", back_populates="user")
    reviews = relationship("Review", back_populates="user")
    events = relationship("Event", back_populates="user")
    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan")
    banned_users = relationship("BannedUser", back_populates="user")


class Clique(db.Model):
    __tablename__ = "cliques"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(200))
    visibility: Mapped[str] = mapped_column(String(200))
    date_created: Mapped[str] = mapped_column(String(100))
    admin_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    icon: Mapped[str] = mapped_column(String(100))

    users = relationship("CliqueUser", back_populates="clique")
    markers = relationship("UserMarker", back_populates="clique")
    notifications = relationship("Notification", back_populates="clique", cascade="all, delete-orphan")
    events = relationship("Event", back_populates="clique")
    banned_users = relationship("BannedUser", back_populates="clique")


class CliqueUser(db.Model):
    __tablename__ = "clique_user"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    clique_id: Mapped[int] = mapped_column(ForeignKey("cliques.id"), primary_key=True)
    joined_date: Mapped[str] = mapped_column(String(100))

    user = relationship("User", back_populates="cliques")
    clique = relationship("Clique", back_populates="users")


class UserMarker(db.Model):
    __tablename__ = "user_marker"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    marker_id: Mapped[int] = mapped_column(ForeignKey("markers.id"), primary_key=True)
    clique_id: Mapped[int] = mapped_column(ForeignKey("cliques.id"), primary_key=True)
    creation_date: Mapped[str] = mapped_column(String(100), default=lambda: datetime.today().strftime("%Y-%m-%d"))

    user = relationship("User", back_populates="markers")
    clique = relationship("Clique", back_populates="markers")
    marker = relationship("Marker", back_populates="users")


class Marker(db.Model):
    __tablename__ = "markers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    long: Mapped[float] = mapped_column(Float, nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=True)
    total_reviews: Mapped[int] = mapped_column(Integer, default=0)
    average_review: Mapped[float] = mapped_column(Float, default=0.0)

    users = relationship("UserMarker", back_populates="marker")
    reviews = relationship("Review", back_populates="marker")
    events = relationship("Event", back_populates="marker")


class Review(db.Model):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stars: Mapped[int] = mapped_column(Integer, nullable=False)  # 1 to 5
    commentary: Mapped[str] = mapped_column(String(500), nullable=True)
    marker_id: Mapped[int] = mapped_column(ForeignKey("markers.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    creation_date: Mapped[str] = mapped_column(String(100), default=lambda: datetime.today().strftime("%Y-%m-%d"))

    marker = relationship("Marker", back_populates="reviews")
    user = relationship("User", back_populates="reviews")


class Notification(db.Model):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(100), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    clique_id: Mapped[int] = mapped_column(ForeignKey("cliques.id"), nullable=False)

    user = relationship("User", back_populates="notifications")
    clique = relationship("Clique", back_populates="notifications")


class Event(db.Model):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[str] = mapped_column(String(100))
    time: Mapped[str] = mapped_column(String(10))
    description: Mapped[str] = mapped_column(String(500), nullable=True)
    marker_id: Mapped[int] = mapped_column(ForeignKey("markers.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    clique_id: Mapped[int] = mapped_column(ForeignKey("cliques.id"), nullable=False)

    marker = relationship("Marker", back_populates="events")
    user = relationship("User", back_populates="events")
    clique = relationship("Clique", back_populates="events")


class BannedUser(db.Model):
    __tablename__ = "banned_users"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    clique_id: Mapped[int] = mapped_column(ForeignKey("cliques.id"), primary_key=True)
    reason: Mapped[str] = mapped_column(String(100), nullable=True)
    ban_date: Mapped[str] = mapped_column(String(100), default=lambda: datetime.today().strftime("%Y-%m-%d"))

    user = relationship("User", back_populates="banned_users")
    clique = relationship("Clique", back_populates="banned_users")


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))
