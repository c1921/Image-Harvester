from __future__ import annotations

from pathlib import Path

from image_harvester.state import StateStore


def test_reset_running_to_pending_restores_interrupted_rows(tmp_path: Path) -> None:
    db = tmp_path / "state.sqlite3"
    store = StateStore(db)
    try:
        job_id = "job_x"
        store.upsert_job(job_id, "{}", "running")
        page = store.ensure_page(job_id, 1, "https://example/1.html", "1")
        store.update_page(page.id, status="running")
        store.upsert_page_images(page.id, [(1, "https://i/1.jpg", str(tmp_path / "a.jpg"))])
        image = store.get_page_images(page.id)[0]
        store.update_image_running(image.id)

        store.reset_running_to_pending(job_id)

        page_after = store.get_page(job_id, 1)
        assert page_after is not None
        assert page_after.status == "pending"
        image_after = store.get_page_images(page.id)[0]
        assert image_after.status == "pending"
    finally:
        store.close()
