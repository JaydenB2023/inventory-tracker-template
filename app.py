import os
from datetime import datetime

from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import or_, cast, String

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-change-me")

# Default to SQLite for a public template repo
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///inventory.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


# -----------------------------
# Model (generic + reusable)
# -----------------------------
class Asset(db.Model):
    __tablename__ = "assets"

    id = db.Column(db.Integer, primary_key=True)
    asset_tag = db.Column(db.String(64), unique=True, nullable=False)
    asset_type = db.Column(db.String(64), nullable=False)
    model = db.Column(db.String(128), nullable=True)
    hostname = db.Column(db.String(128), nullable=True)
    owner_group = db.Column(db.String(128), nullable=True)
    status = db.Column(db.String(64), nullable=False, default="In Use")
    last_updated = db.Column(db.String(32), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.String(32), nullable=False, default=lambda: datetime.utcnow().isoformat())


# -----------------------------
# Helpers (filters + sorting)
# -----------------------------
def _collect_filters(filterable_fields):
    filters = {}
    for field in filterable_fields:
        raw = request.args.get(field, "")
        if isinstance(raw, str):
            raw = raw.strip()
        if raw:
            filters[field] = raw
    return filters


def _apply_column_filters(query, model, filters):
    for field, value in filters.items():
        column = getattr(model, field, None)
        if column is None:
            continue
        query = query.filter(cast(column, String).ilike(f"%{value}%"))
    return query


def _apply_sorting(query, model, allowed_fields, default_sort):
    sort = request.args.get("sort", default_sort)
    direction = request.args.get("dir", "asc")

    if sort not in allowed_fields:
        sort = default_sort

    column = getattr(model, sort, getattr(model, default_sort))
    primary = column.desc() if direction == "desc" else column.asc()

    # Deterministic secondary sort by PK to stabilize pagination
    secondary = model.id.desc() if direction == "desc" else model.id.asc()
    return query.order_by(primary, secondary), sort, direction


# -----------------------------
# Routes
# -----------------------------
@app.route("/", methods=["GET"])
def index():
    page = request.args.get("page", 1, type=int)
    per_page = 25
    q = request.args.get("q", "").strip()

    columns = [
        ("asset_tag", "Asset Tag"),
        ("asset_type", "Type"),
        ("model", "Model"),
        ("hostname", "Hostname"),
        ("owner_group", "Owner / Group"),
        ("status", "Status"),
        ("last_updated", "Last Updated"),
    ]
    filterable_fields = [c[0] for c in columns]

    query = Asset.query

    # Global search
    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(
                Asset.asset_tag.ilike(like),
                Asset.asset_type.ilike(like),
                Asset.model.ilike(like),
                Asset.hostname.ilike(like),
                Asset.owner_group.ilike(like),
                Asset.status.ilike(like),
                Asset.last_updated.ilike(like),
            )
        )

    # Column filters + sorting
    filters = _collect_filters(filterable_fields)
    query = _apply_column_filters(query, Asset, filters)
    query, sort, direction = _apply_sorting(query, Asset, filterable_fields, "asset_tag")

    data = query.paginate(page=page, per_page=per_page, error_out=False)

    return render_template(
        "index.html",
        data=data,
        columns=columns,
        filters=filters,
        sort=sort,
        direction=direction,
    )


@app.route("/assets/new", methods=["GET", "POST"])
def add_asset():
    if request.method == "POST":
        asset = Asset(
            asset_tag=request.form.get("asset_tag", "").strip(),
            asset_type=request.form.get("asset_type", "").strip(),
            model=request.form.get("model", "").strip() or None,
            hostname=request.form.get("hostname", "").strip() or None,
            owner_group=request.form.get("owner_group", "").strip() or None,
            status=request.form.get("status", "").strip(),
            last_updated=request.form.get("last_updated", "").strip() or None,
            notes=request.form.get("notes", "").strip() or None,
        )

        if not asset.asset_tag or not asset.asset_type or not asset.status:
            flash("Asset Tag, Type, and Status are required.", "error")
            return redirect(url_for("add_asset"))

        try:
            db.session.add(asset)
            db.session.commit()
            flash("Asset added.", "success")
            return redirect(url_for("index"))
        except Exception:
            db.session.rollback()
            flash("Could not add asset (Asset Tag must be unique).", "error")
            return redirect(url_for("add_asset"))

    return render_template("add.html")


@app.route("/assets/<int:asset_id>/edit", methods=["GET", "POST"])
def edit_asset(asset_id: int):
    asset = Asset.query.get_or_404(asset_id)

    if request.method == "POST":
        asset.asset_tag = request.form.get("asset_tag", "").strip()
        asset.asset_type = request.form.get("asset_type", "").strip()
        asset.model = request.form.get("model", "").strip() or None
        asset.hostname = request.form.get("hostname", "").strip() or None
        asset.owner_group = request.form.get("owner_group", "").strip() or None
        asset.status = request.form.get("status", "").strip()
        asset.last_updated = request.form.get("last_updated", "").strip() or None
        asset.notes = request.form.get("notes", "").strip() or None

        if not asset.asset_tag or not asset.asset_type or not asset.status:
            flash("Asset Tag, Type, and Status are required.", "error")
            return redirect(url_for("edit_asset", asset_id=asset_id))

        try:
            db.session.commit()
            flash("Asset updated.", "success")
            return redirect(url_for("index"))
        except Exception:
            db.session.rollback()
            flash("Could not update asset (Asset Tag must be unique).", "error")
            return redirect(url_for("edit_asset", asset_id=asset_id))

    return render_template("edit.html", asset=asset)


@app.route("/assets/<int:asset_id>/delete", methods=["POST"])
def delete_asset(asset_id: int):
    asset = Asset.query.get_or_404(asset_id)
    db.session.delete(asset)
    db.session.commit()
    flash("Asset deleted.", "success")
    return redirect(url_for("index"))


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)
