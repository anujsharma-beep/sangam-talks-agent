"""
Human-in-the-loop content approval workflow.

Routes:
  GET  /review                         -> queue of videos with content awaiting a decision
  GET  /review/{video_id}              -> per-platform review screen for one video
  POST /review/{video_id}/{platform}/decision  -> approve or reject one platform's content
  POST /review/{video_id}/publish      -> publish everything currently APPROVED for this video

Nothing here talks to any social platform directly — publishing goes through
the existing, already-tested orchestrator.post_to_platforms(), which only
ever posts content with status == APPROVED.
"""
from fastapi import APIRouter, Body
from fastapi.responses import HTMLResponse, JSONResponse
from html import escape as h
from src.db import get_session_factory, Video, GeneratedContent, ContentStatus, VideoStatus, Post
from src.orchestrator import post_to_platforms
from src.config import prompts_config
from src.logger import logger

router = APIRouter()

PLATFORM_LABELS = {
    "x": "X",
    "linkedin": "LinkedIn",
    "facebook": "Facebook",
    "instagram": "Instagram",
}
PLATFORM_COLORS = {
    "x": "#000000",
    "linkedin": "#0A66C2",
    "facebook": "#1877F2",
    "instagram": "#C13584",
}

STATUS_BADGE = {
    ContentStatus.PENDING: ("#fff3cd", "#856404", "Pending review"),
    ContentStatus.APPROVED: ("#d4edda", "#155724", "Approved — ready to publish"),
    ContentStatus.REJECTED: ("#f8d7da", "#721c24", "Rejected"),
    ContentStatus.POSTED: ("#d1ecf1", "#0c5460", "Posted"),
}

PAGE_STYLE = """
body { font-family: Arial; margin: 40px; background: #f5f5f5; }
.container { background: white; padding: 30px; border-radius: 8px; max-width: 900px; margin: 0 auto; }
h1 { color: #333; }
p.sub { color: #666; }
a { color: #4CAF50; }
.queue-item { border: 1px solid #eee; border-radius: 6px; padding: 16px; margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center; }
.queue-item h3 { margin: 0 0 4px 0; font-size: 15px; }
.queue-item .meta { font-size: 12px; color: #999; }
.badge { display: inline-block; padding: 3px 10px; border-radius: 12px; font-size: 11px; font-weight: bold; margin-right: 6px; }
.btn { padding: 10px 18px; border: none; border-radius: 4px; cursor: pointer; font-size: 14px; font-weight: bold; }
.btn-approve { background: #4CAF50; color: white; }
.btn-approve:hover { background: #45a049; }
.btn-reject { background: #dc3545; color: white; }
.btn-reject:hover { background: #c82333; }
.btn-publish { background: #4CAF50; color: white; padding: 14px 24px; font-size: 16px; width: 100%; }
.btn-review { background: #4CAF50; color: white; padding: 8px 16px; border-radius: 4px; text-decoration: none; font-size: 13px; }
.platform-card { border: 1px solid #eee; border-left: 5px solid #ccc; border-radius: 6px; padding: 18px; margin-bottom: 16px; }
.platform-card h3 { margin: 0 0 8px 0; }
textarea { width: 100%; box-sizing: border-box; font-family: Arial; font-size: 14px; padding: 10px; border: 1px solid #ddd; border-radius: 4px; margin-bottom: 8px; }
.reason-input { width: 100%; box-sizing: border-box; padding: 8px; border: 1px solid #ddd; border-radius: 4px; font-size: 13px; margin-bottom: 8px; }
.char-count { font-size: 12px; color: #999; text-align: right; margin-bottom: 8px; }
.char-count.over { color: #dc3545; font-weight: bold; }
.rejection-note { background: #f8d7da; color: #721c24; padding: 8px 12px; border-radius: 4px; font-size: 13px; margin-bottom: 8px; }
.posted-note { background: #d1ecf1; color: #0c5460; padding: 8px 12px; border-radius: 4px; font-size: 13px; margin-bottom: 8px; }
.empty-state { text-align: center; padding: 60px 20px; color: #999; }
#publishResult { margin-top: 16px; padding: 14px; border-radius: 4px; display: none; }
.success { background: #d4edda; color: #155724; }
.error { background: #f8d7da; color: #721c24; }
"""


def _get_session():
    SessionFactory = get_session_factory()
    return SessionFactory()


@router.get("/review", response_class=HTMLResponse)
async def review_queue():
    """List every video that still has content awaiting a decision or ready to publish."""
    db = _get_session()
    try:
        all_content = db.query(GeneratedContent).all()
        by_video = {}
        for gc in all_content:
            by_video.setdefault(gc.video_id, []).append(gc)

        items_html = []
        for video_id, rows in by_video.items():
            pending = sum(1 for r in rows if r.status == ContentStatus.PENDING)
            approved = sum(1 for r in rows if r.status == ContentStatus.APPROVED)
            rejected = sum(1 for r in rows if r.status == ContentStatus.REJECTED)
            posted = sum(1 for r in rows if r.status == ContentStatus.POSTED)

            if pending == 0 and approved == 0:
                continue

            video = db.query(Video).filter(Video.id == video_id).first()
            title = video.title if video and video.title else video_id

            badges = ""
            if pending:
                badges += f'<span class="badge" style="background:#fff3cd;color:#856404;">{pending} pending</span>'
            if approved:
                badges += f'<span class="badge" style="background:#d4edda;color:#155724;">{approved} approved</span>'
            if rejected:
                badges += f'<span class="badge" style="background:#f8d7da;color:#721c24;">{rejected} rejected</span>'
            if posted:
                badges += f'<span class="badge" style="background:#d1ecf1;color:#0c5460;">{posted} posted</span>'

            items_html.append(f"""
            <div class="queue-item">
                <div>
                    <h3>{h(title)}</h3>
                    <div class="meta">Video ID: {h(video_id)}</div>
                    <div style="margin-top:8px;">{badges}</div>
                </div>
                <a class="btn-review" href="/review/{h(video_id)}">Review &rarr;</a>
            </div>
            """)

        body = "".join(items_html) if items_html else (
            '<div class="empty-state">No content is currently awaiting review.<br>'
            'New videos processed via /test or the scheduler will appear here.</div>'
        )

        return f"""
        <!DOCTYPE html><html><head><title>Content Review Queue</title>
        <style>{PAGE_STYLE}</style></head><body>
        <div class="container">
            <h1>Content Review Queue</h1>
            <p class="sub">Videos with generated content awaiting approval before anything is published.</p>
            {body}
        </div>
        </body></html>
        """
    finally:
        db.close()


@router.get("/review/{video_id}", response_class=HTMLResponse)
async def review_video(video_id: str):
    """Per-platform review screen for a single video."""
    db = _get_session()
    try:
        video = db.query(Video).filter(Video.id == video_id).first()
        if not video:
            return HTMLResponse(f"<p>Video {h(video_id)} not found.</p>", status_code=404)

        gen_contents = db.query(GeneratedContent).filter(
            GeneratedContent.video_id == video_id
        ).order_by(GeneratedContent.platform).all()

        cards = []
        for gc in gen_contents:
            platform = gc.platform
            label = PLATFORM_LABELS.get(platform, platform)
            color = PLATFORM_COLORS.get(platform, "#999")
            limit = prompts_config.get("platforms", {}).get(platform, {}).get("character_limit", 0)
            current_text = gc.approved_content or gc.draft_content
            bg, fg, label_text = STATUS_BADGE.get(gc.status, ("#eee", "#333", str(gc.status)))
            readonly = "readonly" if gc.status == ContentStatus.POSTED else ""

            extra_note = ""
            if gc.status == ContentStatus.REJECTED and gc.rejection_reason:
                extra_note = f'<div class="rejection-note"><strong>Rejected:</strong> {h(gc.rejection_reason)}</div>'
            if gc.status == ContentStatus.POSTED:
                post = db.query(Post).filter(Post.generated_content_id == gc.id).first()
                url_html = f' &mdash; <a href="{h(post.post_url)}" target="_blank">view live post</a>' if post and post.post_url else ""
                extra_note = f'<div class="posted-note">Already published{url_html}</div>'

            action_buttons = "" if gc.status == ContentStatus.POSTED else f"""
                <input type="text" class="reason-input" id="reason-{platform}"
                       placeholder="Reason (required only if you reject)">
                <div style="display:flex; gap:8px;">
                    <button class="btn btn-approve" style="flex:1;" onclick="decide('{h(video_id)}','{platform}','approve')">Approve</button>
                    <button class="btn btn-reject" style="flex:1;" onclick="decide('{h(video_id)}','{platform}','reject')">Reject</button>
                </div>
            """

            cards.append(f"""
            <div class="platform-card" style="border-left-color:{color};">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <h3>{label}</h3>
                    <span class="badge" style="background:{bg};color:{fg};">{label_text}</span>
                </div>
                {extra_note}
                <textarea id="content-{platform}" rows="6" {readonly}>{h(current_text)}</textarea>
                <div class="char-count" id="count-{platform}"></div>
                {action_buttons}
            </div>
            """)

        return f"""
        <!DOCTYPE html><html><head><title>Review: {h(video.title or video_id)}</title>
        <style>{PAGE_STYLE}</style></head><body>
        <div class="container">
            <p><a href="/review">&larr; Back to queue</a></p>
            <h1>{h(video.title or video_id)}</h1>
            <p class="sub">Video ID: {h(video_id)}</p>

            {"".join(cards)}

            <button class="btn btn-publish" onclick="publish('{h(video_id)}')">Publish approved</button>
            <div id="publishResult"></div>
        </div>

        <script>
        const LIMITS = {{
            {", ".join(f'"{p}": {prompts_config.get("platforms", {}).get(p, {}).get("character_limit", 0)}' for p in PLATFORM_LABELS)}
        }};

        function updateCount(platform) {{
            const el = document.getElementById('content-' + platform);
            const countEl = document.getElementById('count-' + platform);
            if (!el || !countEl) return;
            const len = el.value.length;
            const limit = LIMITS[platform] || 0;
            countEl.textContent = len + ' / ' + limit;
            countEl.className = 'char-count' + (len > limit ? ' over' : '');
        }}
        Object.keys(LIMITS).forEach(p => {{
            const el = document.getElementById('content-' + p);
            if (el) {{ updateCount(p); el.addEventListener('input', () => updateCount(p)); }}
        }});

        async function decide(videoId, platform, action) {{
            const content = document.getElementById('content-' + platform).value;
            const reasonEl = document.getElementById('reason-' + platform);
            const reason = reasonEl ? reasonEl.value.trim() : '';

            if (action === 'reject' && !reason) {{
                alert('Please enter a reason for rejecting this post.');
                return;
            }}

            try {{
                const response = await fetch(`/review/${{videoId}}/${{platform}}/decision`, {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ action, content, reason }})
                }});
                if (response.ok) {{
                    window.location.reload();
                }} else {{
                    const data = await response.json();
                    alert('Error: ' + (data.error || 'unknown error'));
                }}
            }} catch (err) {{
                alert('Network error: ' + err.message);
            }}
        }}

        async function publish(videoId) {{
            const resultDiv = document.getElementById('publishResult');
            resultDiv.style.display = 'block';
            resultDiv.className = '';
            resultDiv.textContent = 'Publishing approved content...';
            try {{
                const response = await fetch(`/review/${{videoId}}/publish`, {{ method: 'POST' }});
                const data = await response.json();
                if (response.ok) {{
                    resultDiv.className = 'success';
                    resultDiv.textContent = data.message;
                    setTimeout(() => window.location.reload(), 1500);
                }} else {{
                    resultDiv.className = 'error';
                    resultDiv.textContent = 'Error: ' + (data.error || 'unknown error');
                }}
            }} catch (err) {{
                resultDiv.className = 'error';
                resultDiv.textContent = 'Network error: ' + err.message;
            }}
        }}
        </script>
        </body></html>
        """
    finally:
        db.close()


@router.post("/review/{video_id}/{platform}/decision")
async def review_decision(video_id: str, platform: str, payload: dict = Body(...)):
    """Record an approve/reject decision for one platform's content."""
    action = payload.get("action")
    content = payload.get("content", "")
    reason = payload.get("reason", "")

    if action not in ("approve", "reject"):
        return JSONResponse({"status": "error", "error": "action must be 'approve' or 'reject'"}, status_code=400)
    if action == "reject" and not reason.strip():
        return JSONResponse({"status": "error", "error": "A reason is required to reject content"}, status_code=400)

    db = _get_session()
    try:
        gc = db.query(GeneratedContent).filter(
            GeneratedContent.video_id == video_id,
            GeneratedContent.platform == platform
        ).first()
        if not gc:
return JSONResponse({"status": "error", "error": "Content not found"}, status_code=404)

        if action == "approve":
            gc.approved_content = content
            gc.status = ContentStatus.APPROVED
            gc.rejection_reason = None
            logger.info(f"Content approved for {video_id}/{platform}")
        else:
            gc.status = ContentStatus.REJECTED
            gc.rejection_reason = reason.strip()
            logger.info(f"Content rejected for {video_id}/{platform}: {reason.strip()}")

        db.commit()
        return {"status": "ok"}
    finally:
        db.close()


@router.post("/review/{video_id}/publish")
async def review_publish(video_id: str):
    """Publish everything currently APPROVED for this video."""
    db = _get_session()
    try:
        approved_count = db.query(GeneratedContent).filter(
            GeneratedContent.video_id == video_id,
            GeneratedContent.status == ContentStatus.APPROVED
        ).count()

        if approved_count == 0:
            return JSONResponse(
                {"status": "error", "error": "Nothing is approved yet for this video"},
                status_code=400
            )

        post_to_platforms(video_id, db)

        posted = db.query(GeneratedContent).filter(
            GeneratedContent.video_id == video_id,
            GeneratedContent.status == ContentStatus.POSTED
        ).count()
        still_approved = approved_count - posted

        message = f"Published {posted} platform(s)."
        if still_approved > 0:
            message += f" {still_approved} approved platform(s) failed to post — check Railway logs, then try Publish again."

        return {"status": "ok", "message": message, "posted": posted, "failed": still_approved}
    finally:
        db.close()
