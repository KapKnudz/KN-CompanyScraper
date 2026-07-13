from scraper.db import get_connection  # adjust to your actual DB import


class ScrapeRunRepository:

    def start(self):
        query = """
            INSERT INTO scrape_runs (status)
            VALUES ('running')
            RETURNING id
        """

        with get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(query)
            scrape_run_id = cursor.fetchone()[0]
            connection.commit()

        return scrape_run_id

    def complete(self, scrape_run_id, status, companies_found, news_added):
        query = """
            UPDATE scrape_runs
            SET finished_at = NOW(),
                status = %s,
                companies_found = %s,
                news_added = %s
            WHERE id = %s
        """

        with get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                query,
                (
                    status,
                    companies_found,
                    news_added,
                    scrape_run_id
                )
            )
            connection.commit()

    def fail(self, scrape_run_id, error, companies_found, news_added):
        query = """
            UPDATE scrape_runs
            SET finished_at = NOW(),
                status = 'failed',
                error_message = %s,
                companies_found = %s,
                news_added = %s
            WHERE id = %s
        """

        with get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                query,
                (
                    error,
                    companies_found,
                    news_added,
                    scrape_run_id
                )
            )
            connection.commit()