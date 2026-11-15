# =============================================================
# MIZAN_extras.py
# Community features: Reports, Reviews, Reputation, Recent Verifications.
# Imported and registered from backend.py.
# =============================================================
from datetime import datetime, timedelta
import os
from flask import request, jsonify


def register_extras(app, db, NewsRecord):
    """Wire all the extra DB models + API endpoints into the existing app/db."""

    # ── Models ──────────────────────────────────────────────
    class User(db.Model):
        id                 = db.Column(db.Integer, primary_key=True)
        email              = db.Column(db.String(200), unique=True, nullable=False)
        display_name       = db.Column(db.String(120), default="")
        role               = db.Column(db.String(120), default="")
        reputation         = db.Column(db.Integer, default=0)
        is_verified        = db.Column(db.Boolean, default=False)
        verifications_done = db.Column(db.Integer, default=0)
        created_at         = db.Column(db.DateTime, default=datetime.utcnow)
        updated_at         = db.Column(db.DateTime, default=datetime.utcnow,
                                       onupdate=datetime.utcnow)

    class Report(db.Model):
        report_id            = db.Column(db.Integer, primary_key=True)
        user_id              = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
        user_email           = db.Column(db.String(200), default="")
        content_id           = db.Column(db.Integer, db.ForeignKey('news_record.id'), nullable=True)
        content_snippet      = db.Column(db.Text, default="")
        report_type          = db.Column(db.String(40), default="misleading")
        reason_text          = db.Column(db.Text, default="")
        verdict_at_report    = db.Column(db.String(40), default="")
        confidence_at_report = db.Column(db.Float, default=0.0)
        status               = db.Column(db.String(20), default="pending")
        created_at           = db.Column(db.DateTime, default=datetime.utcnow)
        updated_at           = db.Column(db.DateTime, default=datetime.utcnow,
                                         onupdate=datetime.utcnow)

    class Review(db.Model):
        review_id       = db.Column(db.Integer, primary_key=True)
        user_id         = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
        user_email      = db.Column(db.String(200), default="")
        user_name       = db.Column(db.String(120), default="")
        user_role       = db.Column(db.String(120), default="")
        news_id         = db.Column(db.Integer, db.ForeignKey('news_record.id'), nullable=True)
        news_snippet    = db.Column(db.Text, default="")
        review_text     = db.Column(db.Text, default="")
        rating          = db.Column(db.Integer, default=5)
        user_verdict    = db.Column(db.String(20), default="")
        ai_verdict      = db.Column(db.String(20), default="")
        disinfo_type    = db.Column(db.String(40), default="")
        helpful_count   = db.Column(db.Integer, default=0)
        unhelpful_count = db.Column(db.Integer, default=0)
        weight          = db.Column(db.Float, default=1.0)
        status          = db.Column(db.String(20), default="pending")
        reviewed_by     = db.Column(db.String(120), default="")
        reviewed_at     = db.Column(db.DateTime, nullable=True)
        created_at      = db.Column(db.DateTime, default=datetime.utcnow)
        updated_at      = db.Column(db.DateTime, default=datetime.utcnow,
                                    onupdate=datetime.utcnow)

    class ReviewVote(db.Model):
        id         = db.Column(db.Integer, primary_key=True)
        review_id  = db.Column(db.Integer, db.ForeignKey('review.review_id'), nullable=False)
        user_email = db.Column(db.String(200), default="")
        value      = db.Column(db.String(10), default="helpful")
        created_at = db.Column(db.DateTime, default=datetime.utcnow)
        __table_args__ = (
            db.UniqueConstraint('review_id', 'user_email', name='uq_reviewvote_user_review'),
        )

    # Migration helper: add new columns to news_record if missing
    def _ensure_news_record_columns():
        try:
            with app.app_context():
                from sqlalchemy import text
                rows = db.session.execute(text("PRAGMA table_info(news_record)"))
                existing_cols = {r[1] for r in rows}
                alters = []
                if "verification_count" not in existing_cols:
                    alters.append("ALTER TABLE news_record ADD COLUMN verification_count INTEGER DEFAULT 0")
                if "last_7_days_count" not in existing_cols:
                    alters.append("ALTER TABLE news_record ADD COLUMN last_7_days_count INTEGER DEFAULT 0")
                if "trending_score" not in existing_cols:
                    alters.append("ALTER TABLE news_record ADD COLUMN trending_score FLOAT DEFAULT 0.0")
                if "recent_verdict_timestamp" not in existing_cols:
                    alters.append("ALTER TABLE news_record ADD COLUMN recent_verdict_timestamp DATETIME")
                for stmt in alters:
                    print(f"[DB MIGRATE] {stmt}")
                    db.session.execute(text(stmt))
                if alters:
                    db.session.commit()
        except Exception as e:
            print(f"[DB MIGRATE] WARNING: {e}")

    with app.app_context():
        db.create_all()
        _ensure_news_record_columns()

    # Add tracking attribute on NewsRecord by reflecting columns (no-op if they exist).
    # Existing model classes in backend.py reference NewsRecord.verification_count etc.
    # Those are added via raw ALTER above; reads/writes work even if the model class
    # doesn't declare them, as long as we use raw SQL for those columns.

    # ── Helpers ─────────────────────────────────────────────
    # Admin token is the SAME secret as the admin password — the frontend
    # sends whatever the admin typed into the login box as both
    # X-Admin-Token (for these moderation endpoints) and admin_password
    # (for /admin/delete_review).  Set MIZAN_ADMIN_PASSWORD in the
    # environment.  No insecure default.
    import hmac as _hmac
    from werkzeug.security import check_password_hash as _check_hash
    _ADMIN_HASH  = os.environ.get("MIZAN_ADMIN_PASSWORD_HASH", "").strip()
    _ADMIN_PLAIN = os.environ.get("MIZAN_ADMIN_PASSWORD", "").strip()
    # Legacy compat: still accept MIZAN_ADMIN_TOKEN if explicitly set,
    # but no longer fall back to the public "MIZAN-admin" string.
    _ADMIN_LEGACY = os.environ.get("MIZAN_ADMIN_TOKEN", "").strip()

    def _is_admin():
        tok = request.headers.get("X-Admin-Token", "")
        if not tok:
            try:
                tok = (request.get_json(silent=True) or {}).get("admin_token", "")
            except Exception:
                tok = ""
        if not tok:
            return False
        if _ADMIN_HASH:
            try:
                if _check_hash(_ADMIN_HASH, tok):
                    return True
            except Exception:
                pass
        if _ADMIN_PLAIN and _hmac.compare_digest(tok, _ADMIN_PLAIN):
            return True
        if _ADMIN_LEGACY and _hmac.compare_digest(tok, _ADMIN_LEGACY):
            return True
        return False

    def _get_or_create_user(email, display_name="", role=""):
        if not email:
            return None
        email = email.strip().lower()
        u = User.query.filter_by(email=email).first()
        if u is None:
            u = User(email=email, display_name=display_name or email.split("@")[0], role=role)
            db.session.add(u)
            db.session.commit()
        else:
            changed = False
            if display_name and display_name != u.display_name:
                u.display_name = display_name; changed = True
            if role and role != u.role:
                u.role = role; changed = True
            if changed:
                db.session.commit()
        return u

    def _review_to_dict(r, include_user=False):
        out = {
            "review_id"      : r.review_id,
            "user_name"      : r.user_name,
            "user_role"      : r.user_role,
            "news_id"        : r.news_id,
            "news_snippet"   : r.news_snippet,
            "review_text"    : r.review_text,
            "rating"         : r.rating,
            "user_verdict"   : r.user_verdict,
            "ai_verdict"     : r.ai_verdict,
            "disinfo_type"   : r.disinfo_type,
            "helpful_count"  : r.helpful_count or 0,
            "unhelpful_count": r.unhelpful_count or 0,
            "weight"         : r.weight,
            "status"         : r.status,
            "created_at"     : r.created_at.isoformat() if r.created_at else None,
        }
        if include_user:
            out["user_email"] = r.user_email
            u = User.query.filter_by(email=r.user_email).first() if r.user_email else None
            out["user_reputation"]  = u.reputation if u else 0
            out["user_is_verified"] = bool(u.is_verified) if u else False
        return out

    # Recompute trending fields when /analyze finishes successfully.
    def bump_recent_verification(news_title, snippet=""):
        try:
            from sqlalchemy import text
            now = datetime.utcnow()
            cutoff = now - timedelta(days=7)
            sql = text("""
                UPDATE news_record
                SET verification_count       = COALESCE(verification_count, 0) + 1,
                    last_7_days_count        = (CASE
                        WHEN recent_verdict_timestamp IS NULL OR recent_verdict_timestamp < :cutoff
                        THEN 1 ELSE COALESCE(last_7_days_count, 0) + 1 END),
                    recent_verdict_timestamp = :now,
                    trending_score           = COALESCE(last_7_days_count, 0) + 1
                                               + COALESCE(repetition_count, 0) * 0.5
                WHERE id = (SELECT id FROM news_record
                            WHERE title = :title
                            ORDER BY created_at DESC LIMIT 1)
            """)
            db.session.execute(sql, {"title": news_title, "cutoff": cutoff, "now": now})
            db.session.commit()
        except Exception as e:
            print(f"[bump_recent_verification] {e}")

    app.bump_recent_verification = bump_recent_verification

    # =====================================================
    # ENDPOINTS
    # =====================================================

    @app.route("/api/users/register", methods=["POST", "OPTIONS"])
    def api_register_user():
        if request.method == "OPTIONS":
            return jsonify({"status": "ok"}), 200
        data = request.get_json(silent=True) or {}
        email = (data.get("email") or "").strip().lower()
        if not email or "@" not in email:
            return jsonify({"error": "Valid email required"}), 400
        u = _get_or_create_user(email, data.get("display_name", ""), data.get("role", ""))
        return jsonify({
            "id": u.id, "email": u.email,
            "display_name": u.display_name, "role": u.role,
            "reputation": u.reputation, "is_verified": u.is_verified,
            "verifications_done": u.verifications_done,
        })

    @app.route("/api/users/track_verification", methods=["POST", "OPTIONS"])
    def api_track_verification():
        if request.method == "OPTIONS":
            return jsonify({"status": "ok"}), 200
        data = request.get_json(silent=True) or {}
        email = (data.get("email") or "").strip().lower()
        if not email or "@" not in email:
            return jsonify({"error": "Valid email required"}), 400
        u = _get_or_create_user(email, data.get("display_name", ""), data.get("role", ""))
        u.verifications_done = (u.verifications_done or 0) + 1
        if not u.is_verified and u.verifications_done >= 1:
            u.is_verified = True
        db.session.commit()
        return jsonify({"ok": True, "is_verified": u.is_verified,
                        "reputation": u.reputation,
                        "verifications_done": u.verifications_done})

    # ── Reports (Verify Now → Report Miss) ──
    # status values: pending | approved | rejected   (legacy: reviewed | resolved still tolerated)
    _REPORT_STATUSES = ("pending", "approved", "rejected", "reviewed", "resolved")

    def _report_to_dict(r):
        return {
            "report_id"           : r.report_id,
            "user_email"          : r.user_email,
            "content_id"          : r.content_id,
            "content_snippet"     : r.content_snippet,
            "report_type"         : r.report_type,
            "reason_text"         : r.reason_text,
            "verdict_at_report"   : r.verdict_at_report,
            "confidence_at_report": r.confidence_at_report,
            "status"              : r.status,
            "created_at"          : r.created_at.isoformat() if r.created_at else None,
            "updated_at"          : r.updated_at.isoformat() if r.updated_at else None,
        }

    @app.route("/api/reports", methods=["POST", "OPTIONS"])
    def api_create_report():
        if request.method == "OPTIONS":
            return jsonify({"status": "ok"}), 200
        data = request.get_json(silent=True) or {}
        email = (data.get("email") or "").strip().lower()
        u = _get_or_create_user(email) if email else None
        rtype = (data.get("report_type") or "misleading").strip()
        if rtype not in ("fake_news", "deepfake_image", "deepfake_video", "misleading"):
            rtype = "misleading"
        rep = Report(
            user_id              = u.id if u else None,
            user_email           = email,
            content_id           = data.get("content_id"),
            content_snippet      = (data.get("content_snippet") or "")[:1000],
            report_type          = rtype,
            reason_text          = (data.get("reason_text") or "")[:2000],
            verdict_at_report    = (data.get("verdict_at_report") or "")[:40],
            confidence_at_report = float(data.get("confidence_at_report") or 0),
            status               = "pending",
        )
        db.session.add(rep)
        db.session.commit()
        return jsonify({"ok": True, "report_id": rep.report_id,
                        "status": rep.status,
                        "created_at": rep.created_at.isoformat(),
                        "message_ar": "✅ تم إرسال البلاغ — بانتظار موافقة الإدارة",
                        "message_en": "✅ Report submitted — awaiting admin approval"})

    @app.route("/api/reports", methods=["GET"])
    def api_list_reports():
        if not _is_admin():
            return jsonify({"error": "admin token required"}), 401
        status_q = (request.args.get("status") or "").strip().lower()
        q = Report.query
        if status_q in _REPORT_STATUSES:
            q = q.filter_by(status=status_q)
        rows = q.order_by(Report.created_at.desc()).limit(500).all()
        return jsonify([_report_to_dict(r) for r in rows])

    # Public: list of admin-approved missed-fake reports (for frontend display)
    @app.route("/api/reports/approved", methods=["GET"])
    def api_list_approved_reports():
        rows = Report.query.filter_by(status="approved") \
                    .order_by(Report.updated_at.desc(),
                              Report.created_at.desc()).limit(60).all()
        return jsonify([_report_to_dict(r) for r in rows])

    @app.route("/api/admin/reports/<int:rid>", methods=["POST", "OPTIONS"])
    def api_admin_update_report(rid):
        if request.method == "OPTIONS":
            return jsonify({"status": "ok"}), 200
        if not _is_admin():
            return jsonify({"error": "admin token required"}), 401
        data = request.get_json(silent=True) or {}
        new_status = (data.get("status") or "").strip().lower()
        if new_status not in _REPORT_STATUSES:
            return jsonify({"error": "invalid status"}), 400
        rep = Report.query.get(rid)
        if not rep:
            return jsonify({"error": "report not found"}), 404
        rep.status = new_status
        db.session.commit()
        return jsonify({"ok": True, "report_id": rep.report_id, "status": rep.status})

    # ── Recent Verifications (last 7 days, server-side global storage) ──
    @app.route("/api/recent-verifications", methods=["GET"])
    def api_recent_verifications():
        from sqlalchemy import text as _text
        days = int(request.args.get("days", 7))
        days = max(1, min(days, 30))
        cutoff = datetime.utcnow() - timedelta(days=days)
        try:
            rows = db.session.execute(_text("""
                SELECT id, title, summary, final_score, input_type,
                       COALESCE(verification_count, 0)  AS vc,
                       COALESCE(last_7_days_count, 0)   AS w7,
                       COALESCE(trending_score, 0.0)    AS ts,
                       recent_verdict_timestamp, created_at, best_url
                FROM news_record
                WHERE recent_verdict_timestamp IS NOT NULL
                  AND recent_verdict_timestamp >= :cutoff
                ORDER BY ts DESC, recent_verdict_timestamp DESC
                LIMIT 60
            """), {"cutoff": cutoff}).mappings().all()
        except Exception as e:
            print(f"[/api/recent-verifications] {e}")
            rows = []

        if not rows:
            rows = db.session.execute(_text("""
                SELECT id, title, summary, final_score, input_type,
                       COALESCE(verification_count, 0)  AS vc,
                       COALESCE(last_7_days_count, 0)   AS w7,
                       COALESCE(trending_score, 0.0)    AS ts,
                       NULL AS recent_verdict_timestamp,
                       created_at, best_url
                FROM news_record
                ORDER BY created_at DESC LIMIT 30
            """)).mappings().all()

        def _verdict(score):
            s = score or 0
            return "verified" if s >= 70 else ("uncertain" if s >= 40 else "fake")

        out = []
        for r in rows:
            ts = r.get("recent_verdict_timestamp") or r.get("created_at")
            out.append({
                "id"           : r["id"],
                "title"        : r["title"],
                "summary"      : r["summary"],
                "final_score"  : r["final_score"],
                "verdict"      : _verdict(r["final_score"]),
                "input_type"   : r["input_type"],
                "verification_count": r["vc"],
                "last_7_days_count" : r["w7"],
                "trending_score"    : r["ts"],
                "recent_verdict_timestamp": (ts.isoformat() if hasattr(ts, "isoformat") else ts),
                "created_at"   : (r["created_at"].isoformat()
                                  if hasattr(r["created_at"], "isoformat") else r["created_at"]),
                "best_url"     : r["best_url"],
            })
        return jsonify(out)

    # ── Public Reviews ──
    @app.route("/api/reviews/submit", methods=["POST", "OPTIONS"])
    def api_submit_review():
        if request.method == "OPTIONS":
            return jsonify({"status": "ok"}), 200
        data = request.get_json(silent=True) or {}
        email = (data.get("email") or "").strip().lower()
        # Email is optional for community verdicts — anyone can submit an opinion;
        # it just sits at status="pending" until an admin approves it.
        if email and "@" not in email:
            return jsonify({"error": "Invalid email format",
                            "code": "email_invalid"}), 400
        u = _get_or_create_user(email,
                                display_name=data.get("user_name", ""),
                                role=data.get("user_role", "")) if email else None
        text_in = (data.get("review_text") or "").strip()
        if not text_in:
            return jsonify({"error": "review_text required"}), 400

        rev = Review(
            user_id      = (u.id if u else None),
            user_email   = email,
            user_name    = (data.get("user_name") or (u.display_name if u else "") or "")[:120],
            user_role    = (data.get("user_role") or (u.role if u else "") or "")[:120],
            news_id      = data.get("news_id"),
            news_snippet = (data.get("news_snippet") or "")[:1000],
            review_text  = text_in[:4000],
            rating       = int(data.get("rating") or 5),
            user_verdict = (data.get("user_verdict") or "")[:20],
            ai_verdict   = (data.get("ai_verdict") or "")[:20],
            disinfo_type = (data.get("disinfo_type") or "")[:40],
            weight       = round(1.0 + ((u.reputation if u else 0) or 0) / 10.0, 3),
            status       = "pending",
        )
        db.session.add(rev)
        db.session.commit()
        return jsonify({"ok": True, "review_id": rev.review_id,
                        "status": rev.status, "weight": rev.weight,
                        "message_ar": "✅ تم إرسال مراجعتك — بانتظار موافقة الإدارة",
                        "message_en": "✅ Review submitted — awaiting admin approval"})

    @app.route("/api/reviews/approved", methods=["GET"])
    def api_list_approved_reviews():
        rows = Review.query.filter_by(status="approved") \
                    .order_by(Review.helpful_count.desc(),
                              Review.created_at.desc()).limit(60).all()
        return jsonify([_review_to_dict(r) for r in rows])

    @app.route("/api/reviews/<int:rid>/vote", methods=["POST", "OPTIONS"])
    def api_vote_review(rid):
        if request.method == "OPTIONS":
            return jsonify({"status": "ok"}), 200
        data = request.get_json(silent=True) or {}
        email = (data.get("email") or "").strip().lower()
        val = (data.get("value") or "").strip().lower()
        if val not in ("helpful", "unhelpful"):
            return jsonify({"error": "value must be helpful|unhelpful"}), 400
        if not email or "@" not in email:
            return jsonify({"error": "email required"}), 400
        rev = Review.query.get(rid)
        if not rev or rev.status != "approved":
            return jsonify({"error": "review not found or not approved"}), 404

        existing = ReviewVote.query.filter_by(review_id=rid, user_email=email).first()
        if existing:
            if existing.value == val:
                return jsonify({"ok": True, "already_voted": True,
                                "helpful_count": rev.helpful_count,
                                "unhelpful_count": rev.unhelpful_count})
            if existing.value == "helpful":
                rev.helpful_count   = max(0, (rev.helpful_count or 0) - 1)
                rev.unhelpful_count = (rev.unhelpful_count or 0) + 1
            else:
                rev.unhelpful_count = max(0, (rev.unhelpful_count or 0) - 1)
                rev.helpful_count   = (rev.helpful_count or 0) + 1
            existing.value = val
        else:
            if val == "helpful":
                rev.helpful_count = (rev.helpful_count or 0) + 1
            else:
                rev.unhelpful_count = (rev.unhelpful_count or 0) + 1
            db.session.add(ReviewVote(review_id=rid, user_email=email, value=val))

        reviewer = User.query.filter_by(email=rev.user_email).first() if rev.user_email else None
        if reviewer:
            reviewer.reputation = (reviewer.reputation or 0) + (1 if val == "helpful" else -1)
        db.session.commit()
        return jsonify({"ok": True,
                        "helpful_count": rev.helpful_count,
                        "unhelpful_count": rev.unhelpful_count})

    # ── Admin moderation ──
    @app.route("/api/admin/reviews/pending", methods=["GET"])
    def api_admin_pending_reviews():
        if not _is_admin():
            return jsonify({"error": "admin token required"}), 401
        status = (request.args.get("status") or "pending").strip().lower()
        if status not in ("pending", "approved", "rejected"):
            status = "pending"
        rows = Review.query.filter_by(status=status) \
                    .order_by(Review.created_at.desc()).limit(200).all()
        return jsonify([_review_to_dict(r, include_user=True) for r in rows])

    @app.route("/api/admin/reviews/<int:rid>/moderate", methods=["POST", "OPTIONS"])
    def api_admin_moderate_review(rid):
        if request.method == "OPTIONS":
            return jsonify({"status": "ok"}), 200
        if not _is_admin():
            return jsonify({"error": "admin token required"}), 401
        data = request.get_json(silent=True) or {}
        new_status = (data.get("status") or "").strip().lower()
        if new_status not in ("approved", "rejected"):
            return jsonify({"error": "status must be approved|rejected"}), 400
        rev = Review.query.get(rid)
        if not rev:
            return jsonify({"error": "review not found"}), 404

        rev.status      = new_status
        rev.reviewed_by = (data.get("admin_name") or "admin")[:120]
        rev.reviewed_at = datetime.utcnow()

        reviewer = User.query.filter_by(email=rev.user_email).first() if rev.user_email else None
        if reviewer:
            if new_status == "approved":
                reviewer.reputation = (reviewer.reputation or 0) + 5
            else:
                reviewer.reputation = (reviewer.reputation or 0) - 3
            rev.weight = round(1.0 + (reviewer.reputation or 0) / 10.0, 3)
        db.session.commit()
        return jsonify({"ok": True, "review_id": rev.review_id, "status": rev.status})

    return {
        "User": User, "Report": Report,
        "Review": Review, "ReviewVote": ReviewVote,
    }
