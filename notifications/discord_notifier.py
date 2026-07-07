import requests


class DiscordNotifier:

    def __init__(self, webhook_url):
        self.webhook_url = webhook_url


    def send(self, message):

        requests.post(
            self.webhook_url,
            json={
                "content": message
            }
        )