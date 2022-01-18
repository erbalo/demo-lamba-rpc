import base64
import json
import os
import logging

from http import HTTPStatus
from sqlite3 import converters
from lib.amq_client import AmqpClient
from typing import Tuple

logging.getLogger("pika").setLevel(logging.WARNING)
level = logging.getLevelName(os.getenv('log_level', 'INFO'))
logger = logging.getLogger()

if len(logging.getLogger().handlers) > 0:
    # The Lambda environment pre-configures a handler logging to stderr. If a handler is already configured,
    # `.basicConfig` does not execute. Thus we set the level directly.
    logger.setLevel(level)
else:
    logging.basicConfig(level=level)
    logger = logging.getLogger()

MAPPING_ROUTES = {
    'GET': {
        '/api/v1/users': 'edu.api.user.service.all'
    },
    'POST': {
        '/api/v1/users': 'edu.api.user.service.create'
    }
}

def handler(event, context):    
    message = {}
    queue = None

    if event['httpMethod'] and event['path']:
        error_response, queue = context_queue(event)

        if error_response:
            return error_response
    else:
        return build_response(HTTPStatus.BAD_GATEWAY)
    
    error_response, body = context_body(event)

    if error_response:
        return error_response
    
    if body:
        message.update(body)

    if event['queryStringParameters']:
        message.update(event['queryStringParameters'])

    logging.info(f"=> message {message} to queue {queue}")

    amqp_client = AmqpClient()
    recived_message = amqp_client.call(queue, message)

    response_message = json.loads(recived_message)
    error, data_converted = map_amqp_response(response_message)

    if error:
        return error
    
    amqp_client.close()

    return build_response(data_converted['status_code'], data_converted['data'])


def map_amqp_response(response) -> Tuple:
    if response.get('state') and response.get('state') == 'success':
        response_data = response.get('data', {})
        status_code = response_data.get('status_code')

        if response_data and status_code:
            response_data.pop('status_code')
            converted = {
                'status_code': HTTPStatus(status_code),
                'data': response_data
            }
            return None, converted
        else:
            return build_response(HTTPStatus.SERVICE_UNAVAILABLE), None
    else:
        return build_response(HTTPStatus.INTERNAL_SERVER_ERROR), None


def context_queue(event) -> Tuple:
    routes = MAPPING_ROUTES.get(event['httpMethod'])

    if not routes:
        return build_response(HTTPStatus.METHOD_NOT_ALLOWED), None

    queue = routes.get(event['path'], None)

    if not queue:
        return build_response(HTTPStatus.BAD_REQUEST), None

    return None, queue

def context_body(event) -> Tuple:
    try:        
        if event["isBase64Encoded"]:
            body_str = base64.b64decode(event["body"])
            return None, json.loads(body_str)
        else:
            return None, json.loads(event["body"])
    except Exception as e:
        logging.error('Error to transform %s', 'body', exc_info=e)
        return build_response(HTTPStatus.BAD_REQUEST), None


def build_response(status_code: HTTPStatus = HTTPStatus.OK, data: dict = {}) -> dict:
    if not data.get('message'):
        message = {
            'message': f'{status_code.phrase} ({status_code.description})'
        }
        data.update(message)

    return {
        'statusCode': str(status_code.value),
        'body': json.dumps(data),
        'isBase64Encoded':  False
    }