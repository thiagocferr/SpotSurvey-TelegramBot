import requests
import json

import logging

LOGGER = logging.getLogger(__name__)

# TODO: Test pagins mechanism
# TODO: Treat API Endpoints erros better (raising, etc...)
class SpotifyRequest:
    """ Class that encapsulate requests for the Spotify API

    Params:
        method (string): Which HTTP Method (Verb) to use
        url (string): URL to where send HTTP request
        data (dictionary) (optional): Data to be sent as request body (for sending JSON-like structure, use parameter 'json')
        headers (dictionary) (optional): Headers of the request
        params (dictionary) (optional): Parameters to be sent with the URL (like a query string)
        json (dictionary) (optional): JSON to be sent as request body

    """

    def __init__(self, method, url, data=None, headers=None, params=None, json=None):
        self.method = method
        self.url = url
        self.data = data
        self.headers = headers
        self.params = params
        self.json = json

        self.prev_url = None

    def __check_response__(self, response):
        """ Check if a request has failed (if recieved JSON has an error code, as seen on \\
        https://developer.spotify.com/documentation/web-api/#regular-error-object) """


        if not response.ok and response.status_code >= 400:

            try:
                error_message = response.json()['error']['message']
            except json.decoder.JSONDecodeError:
                error_message = response.reason

            LOGGER.error('Error code: {}'.format(response.status_code))
            LOGGER.error('Error code {} during Spotify call to URL {} : Message = {}'.format(response.status_code, self.url, error_message))

            raise SpotifyOperationException()


    def change_data(self, new_data):
        """ Change request body

        Args:
            new_data (dictionary): New data of request
        """
        self.data = new_data
    def change_json(self, new_json):
        """ Change request body (as a JSON)

        Args:
            new_json (dictionary): New JSON object of request
        """
        self.json = new_json

    def get_next_page(self):
        """ For requests that are paginated (see Pagin Object on \
        https://developer.spotify.com/documentation/web-api/reference/object-model/#paging-object)

        The way this works is: as pagination on the Spotify API consists of a field 'next' with the URL of the next page
        if there is another page, yield result and change this object's URL to be the next page

        Returns:
            Response object
        """
        while self.url is not None:
            yield self.send()

    def send(self):

        if self.url is None:
            return None

        response = requests.request(
            method=self.method,
            url=self.url,
            data=self.data,
            headers=self.headers,
            params = self.params,
            json = self.json
        )

        self.__check_response__(response)

        try:
            # In case of response is paginated
            next_url = response.json().get('next')
            self.prev_url = self.url
            self.url = next_url
        except json.decoder.JSONDecodeError:
            pass

        return response

class SpotifyOperationException(Exception):
    """ Exception to represent when a call to a Spotify API endpoint fails """