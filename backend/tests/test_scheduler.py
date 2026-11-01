from app.core.scheduler import POLL_JOB_ID, create_scheduler


def test_scheduler_registers_poll_job_only():
    scheduler = create_scheduler(30)

    assert {job.id for job in scheduler.get_jobs()} == {POLL_JOB_ID}
