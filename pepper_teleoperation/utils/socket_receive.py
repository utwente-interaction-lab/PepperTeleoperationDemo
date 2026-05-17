import zmq
import zmq.error
import json
import socket
import sys
import time

## class SocketReceive
#
# socket to receive keypoints in a dictionary
class SocketReceive:
    ctx = None
    sock = None

    ## method init
    # 
    # class initialization 
    def __init__(self):
        # initialize socket
        self.ctx = zmq.Context()
        self.sock = self.ctx.socket(zmq.SUB)

        # Prefer localhost since tracker runs on same PC.
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
        try: 
            self.sock.connect("tcp://127.0.0.1:1234")
            if local_ip and local_ip not in ("127.0.0.1", "0.0.0.0"):
                self.sock.connect("tcp://%s:1234" % local_ip)
            self.sock.setsockopt(zmq.SUBSCRIBE, b'')  # subscribe to every topic sent by the publisher
            # Allow loop to poll for stop / show "no keypoints" if publisher is down
            self.sock.setsockopt(zmq.RCVTIMEO, 500)

        except Exception as e:
            print(e)
            sys.exit(-1)
    
    ## method receive_keypoints
    #
    # start receiving 3D keypoints dict
    def receive_keypoints(self):
        try:
            json_msg = self.sock.recv()
            wp_dict = json.loads(json_msg)
            return wp_dict
        except zmq.error.Again:
            return {}
        except Exception as e:
            print(e)
            time.sleep(0.05)
            return {}

    ## method close
    # 
    # close socket
    def close(self):
        self.sock.close()
        self.ctx.term()