from ast import arg
import threading
import pika
import uuid
import json


class AmqpClient(object):


    def __init__(self):
        self.connection = pika.BlockingConnection(
            pika.ConnectionParameters(
                host='localhost'
            ))
        self.channel = self.connection.channel()
        self.channel.basic_qos(prefetch_count=1)

        result = self.channel.queue_declare(queue='', exclusive=True)
        self.callback_queue = result.method.queue

        self.channel.basic_consume(
            queue=self.callback_queue,
            on_message_callback=self.start_threading,
            auto_ack=True)


    def on_response(self, ch, method, props, body):
        if self.corr_id == props.correlation_id:
            self.response = body


    def start_threading(self, ch, method, props, body):
        thread = threading.Thread(target=self.on_response, args=(ch, method, props, body))
        thread.setDaemon(True)
        thread.start()


    def call(self, queue, message):
        command = {
            'command': 'command-execution',
            'args': message
        }

        self.response = None
        self.corr_id = str(uuid.uuid4())
        self.channel.basic_publish(
            exchange='',
            routing_key=queue,
            properties=pika.BasicProperties(
                reply_to=self.callback_queue,
                correlation_id=self.corr_id,
            ),
            body=json.dumps(command))
        
        while self.response is None:
            self.connection.process_data_events()
        
        return self.response


    def close(self):
        self.connection.close()