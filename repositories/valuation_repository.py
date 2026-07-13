class ValuationRepository:

    def __init__(self, client):
        self.client = client

    def get_current(self, instrument_id):
        ...

    def get_historical(self, instrument_id):
        ...