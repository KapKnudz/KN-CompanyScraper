from unittest.mock import MagicMock, patch

from kncompanyscraper.repositories.job_repository import JobRepository


def connection_with(cursor):
    connection = MagicMock()
    connection.__enter__.return_value = connection
    connection.cursor.return_value.__enter__.return_value = cursor
    return connection


def test_job_repository_reads_job_and_checkpoint():
    cursor = MagicMock()
    cursor.fetchone.return_value = {
        "id": 7,
        "job_type": "company_full_analysis",
        "status": "failed",
        "result": {"next_resumable_stage": "scenario"},
    }
    with patch(
        "kncompanyscraper.repositories.base_repository.get_connection",
        return_value=connection_with(cursor),
    ):
        job = JobRepository().get(7)

    assert job["result"]["next_resumable_stage"] == "scenario"
    assert cursor.execute.call_args.args[1] == (7,)


def test_job_repository_merges_partial_result_and_reopens_job():
    cursor = MagicMock()
    with patch(
        "kncompanyscraper.repositories.base_repository.get_connection",
        return_value=connection_with(cursor),
    ):
        repository = JobRepository()
        repository.update_partial_result(7, {"stage": "qualitative"})
        repository.mark_running(7)

    merge_sql, merge_params = cursor.execute.call_args_list[0].args
    assert "COALESCE(result, '{}'::jsonb) || %s" in merge_sql
    assert merge_params[1] == 7
    reopen_sql, reopen_params = cursor.execute.call_args_list[1].args
    assert "status = 'running'" in reopen_sql
    assert reopen_params == (7,)


def test_job_repository_checkpoints_stage_input_inside_stage_result():
    cursor = MagicMock()
    with patch(
        "kncompanyscraper.repositories.base_repository.get_connection",
        return_value=connection_with(cursor),
    ):
        JobRepository().checkpoint_stage_input(
            7,
            "qualitative",
            {
                "base_prompt_artifact": "artifact",
                "base_prompt_sha256": "hash",
                "prompt_contract_version": "qualitative-stage-prompt-v1",
            },
        )

    sql, params = cursor.execute.call_args.args
    assert "jsonb_set" in sql
    assert params[0] == "qualitative"
    assert params[1] == "qualitative"
    assert params[3] == 7
