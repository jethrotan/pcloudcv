import threading

from socketIO_client import SocketIO
import redis
from colorama import init
import requests
from utility import logging
import utility.job as job
import traceback
import os
import local_server
from urlparse import urlparse
from os.path import splitext, basename


init()
socketio = None

#import logging.log
#logging.log.basicConfig(level=logging.log.DEBUG)

class SocketIOConnection(threading.Thread):
    _executable = ''
    _imagepath = ''
    _redis_obj = None
    _pubsub_obj = None

    def __init__(self, executable, imagepath):
        threading.Thread.__init__(self)

        self._executable = str(executable)
        self._imagepath = str(imagepath)

        redis_thread = self.setupRedis()
        redis_thread.setDaemon(True)
        redis_thread.start()

    def setupRedis(self):
        self._redis_obj = redis.StrictRedis(host='localhost', port=6379, db=0)
        self._pubsub_obj = self._redis_obj.pubsub()
        self._pubsub_obj.subscribe('intercomm2')

        redis_thread = RedisListen(self._pubsub_obj, self._redis_obj)
        return redis_thread

    def run(self):
        logging.log('I', 'Starting Socket Connection Thread')

        self.setupSocketIO()
        logging.log('I', 'Exiting Socket Connection Thread')
        local_server.server.stop()
        print 'Exit Program by pressing Control + C'

    def connection(self, *args):
        print 'Connected using websockets'

    def on_error_response(self, *args):
        error_message = args[0]
        if('error' in error_message):
            print error_message['error']
        if('end' in error_message):
            self._redis_obj.publish('intercomm', '***end***')

    def on_aaa_response(self, *args):
        message = args[0]

        if ('socketid' in message):
            self._redis_obj.publish('intercomm', message['socketid'])
            self._socketid = message['socketid']

        if ('name' in message):
            logging.log('O', message['name'])
            self._socket_io.emit('send_message', self._executable)

        if ('data' in message):
            logging.log('O', message['data'])
            job.job.output = message['data']
            self._redis_obj.publish('intercomm', '***end***')

        if ('picture' in message):
            logging.log('D', message['picture'])

            resultpath = self._imagepath.rstrip('/') + '/' + message['jobid']

            job.job.setJobID(message['jobid'])
            job.job.resultpath = resultpath
            job.job.executable = self._executable

            try:
                if not os.path.exists(resultpath):
                    os.makedirs(resultpath)
                    os.chmod(resultpath, 0776)
                i =0
                while i<10:
                    try:
                        file = requests.get(message['picture'])
                        break
                    except Exception as e:
                        print 'Error Connecting to CloudCV. Will try again'
                    i+=1

                file_name = basename(urlparse(message['picture']).path)

                f = open(resultpath + '/' + file_name, 'wb')
                f.write(file.content)
                f.close()

                job.job.addFiles(resultpath + '/' + file_name)

            except Exception as e:
                logging.log('W', str(traceback.format_exc()))
                logging.log('W', str('possible reason: Output format improper'))

            logging.log('D', 'File Saved: ' + resultpath + '/' + file_name)

        if ('mat' in message):
            logging.log('D', message['mat'])
            file = requests.get(message['mat'])
            with open(self._imagepath + '/results' + self._socketid + '.txt', 'wb') as f:
                f.write(file.content)
            logging.log('D', 'Results Saved: ' + self._imagepath + '/results' + self._socketid + '.txt')

        if ('request_data' in message):
            self._socket_io.emit('send_message', 'data')


    def setupSocketIO(self):
        global socketio

        try:
            self._socket_io = SocketIO('godel.ece.vt.edu', 8000)
            self._socket_io.on('connect', self.connection)
            self._socket_io.on('message', self.on_aaa_response)
            self._socket_io.on('error', self.on_error_response)
            socketio = self._socket_io
            self._socket_io.wait()

        except Exception as e:
            logging.log('W', e)
            raise SystemExit


class RedisListen(threading.Thread):
    def __init__(self, ps, r):
        threading.Thread.__init__(self)
        self._redis_obj = r
        self._pubsub_obj = ps

    def run(self):
        logging.log('I', 'Listening to Redis Channel')
        while (True):
            shouldEnd = self.listenToChannel(self._pubsub_obj, self._redis_obj)
            if (shouldEnd):
                break
        logging.log('I', 'Ending Listing to Redis Channel')

    def listenToChannel(self, ps, r):
        global socketio

        for item in ps.listen():
            if item['type'] == 'message':
                if '***endcomplete***' in item['data']:
                    socketio.disconnect()
                    return True
                try:
                    if item['type'] == 'message':
                        socketio.emit('getsocketid', 'socketid')
                except Exception as e:
                    print e
        return False
