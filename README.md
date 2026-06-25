# GeoCliques

![Python](https://img.shields.io/badge/Python-3.12-blue?logo=python)
![Flask](https://img.shields.io/badge/Flask-3.x-black?logo=flask)
![Leaflet](https://img.shields.io/badge/Leaflet-Maps-green?logo=leaflet)

**GeoCliques** is a social, map-based web application where users can create and join "cliques" (groups), place markers on a map, leave reviews and events, and collaborate in a dynamic geospatial environment. The app includes user authentication, interactive mapping with custom icons, notifications, multi-layer map support, and full admin control over user content.

> 🎓 This application was originally co-developed as a 2025 joint academic capstone project. This repository represents my independent, refactored fork.

## ✨ Features

- **Interactive Map**: Add markers, view reviews, and schedule events directly on a Leaflet.js map.
- **Cliques System**: Create, join, or manage public, protected, and private cliques.
- **Review System**: Leave star ratings and optional commentary for each marker.
- **Event Scheduling**: Plan and view events tied to specific locations.
- **Notifications**: Receive and manage invitations, join requests, bans, and kicks.
- **Admin Control Room**: Manage clique membership, review content, and moderate user activities.
- **Custom Styling**: Dynamic marker icons, color-coded cliques, modern UI/UX styling.
- **Map Layers**: Switch between multiple map providers (OpenStreetMap, Esri Satellite, Thunderforest).

## 💻 Tech Stack

* **Backend:** Flask (Routing) & SQLAlchemy (ORM models)
* **Frontend:** Vanilla JavaScript, Bootstrap & Jinja2 (Server-side rendering)
* **Database:** PostgreSQL (Production) & SQLite (Local sandbox)
* **Mapping Engine:** Leaflet.js (Open-source interactive maps)
* **Security & Search:** Werkzeug (Cryptographic hashing) & RapidFuzz (Fuzzy string matching)

## 📂 Folder Structure

```
geocliques/
├── instance/            # Local SQLite database (gitignored)
├── static/              # Frontend web assets
│   ├── css/             # Stylesheets
│   ├── assets/          # Static media & default avatars
│   └── js/              # Interactive UI logic
├── templates/           # Jinja2 HTML templates
│   ├── master/          # Platform management dashboard
│   └── user/            # Public-facing views
├── models.py            # SQLAlchemy ORM models
├── main.py              # App entry point & route controllers
├── requirements.txt     # Python dependencies
├── utils.py             # Shared helper functions
└── README.md            # Project documentation
```

## 🚧 Roadmap & Architectural Exploration
This repository serves as a stable, functional baseline. Updates are pushed iteratively as new architectural patterns are evaluated.

**Active areas of exploration:**
* **Query Optimization:** Refactoring ORM queries to resolve N+1 performance bottlenecks and improve data retrieval speeds.
* **AI Integration:** Integrating AI capabilities for intelligent platform features.
* **Database Scaling:** Migrating infrastructure from SQLite to PostgreSQL.
* **Map Infrastructure:** Transitioning to keyless, open-source map tile providers.
* **Code Quality:** Enforcing strict Python type-safety and modern linting.
