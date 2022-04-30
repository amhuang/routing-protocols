import sys
import socket
import json
import time
import datetime
import threading

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

class RouteNode:
    def __init__(self): 
        self.neighbors = {}     # {port : cost}
        self.last = False
        self.sent = False
        self.cost_change = 0
        self.dv = {}            # distance vector in format {port : (cost, next_hop)}

    def run(self): 
        if len(sys.argv) < 3:
            self.err_msg("Usage: python3 routenode.py dv <r/p> <update-interval> <local-port> <neighbor1-port> <cost-1> <neighbor2-port> <cost-2> ... [last] [<cost-change>]")
        
        algo = sys.argv[1]              # Algoorithm to use
        mode = sys.argv[2]              # Regular or Poisoned Reverse
        update_interval = sys.argv[3]   # 
        self.port = int(sys.argv[4])    # Local port
        self.ip = "127.0.0.1"
        self.validate_port(self.port)

        i = 5
        while i < len(sys.argv) - 1 and sys.argv[i] != "last":
            port = int(sys.argv[i])
            self.validate_port(port)
            cost = int(sys.argv[i + 1])
            self.neighbors[port] = cost
            i += 2
        for n in self.neighbors: 
            self.dv[n] = [self.neighbors[n], n]

        if i < len(sys.argv) and sys.argv[i] == "last":
            self.last = True
            i += 1
        if i < len(sys.argv):
            self.cost_change = sys.argv[i]
        
        # run distance vector algorithm
        if algo == "dv":
            if mode == "r":
                self.distance_vector()  # run normal distance vector
            elif mode == "p":
                pass                    # run poisoned reverse
            else:
                self.err_msg("Usage: Mode must be 'r' (regular) or 'p' (poisoned reverse)")
        else:
            self.err_msg("Usage: Algorithm must be 'dv' or ... ")

    def distance_vector(self):
        sock.bind((self.ip, self.port))    # socket listening
        if self.last:
            self.sent = True
            self.dv_broadcast()

        recv_th = threading.Thread(target=self.dv_recv)
        recv_th.start()

    def dv_broadcast(self):
        table = json.dumps(self.dv).encode()
        for n in self.neighbors:
            print("Message sent from Node", self.port, "to Node", n)
            sock.sendto(table, (self.ip, n))

    def dv_recv(self):
        while True:
            # Receives routing table from addr
            buf, addr = sock.recvfrom(2048)
            table = json.loads(buf)
            
            self.dv_compute(table, addr)
            print("Message received at Node", self.port, "from Node", addr[1])

    # Compute to change own DV based off table from addr
    def dv_compute(self, table, addr):
        # distance between neighbor port and self
        c = self.dv[addr[1]][0]
        updated = False
        print("received table from", addr,"\n",table)

        for port in table:
            # if distance to port in new table is unknown
            dist = table[port][0]
            port = int(port)

            if port != self.port:
                # if a former path to the node is known
                if port in self.dv:
                    if c + dist < self.dv[port][0]:
                        # next hop to get to sender
                        next_hop = self.dv[addr[1]][1]
                        self.dv[port] = [c + dist, next_hop]
                        updated = True 
                else:
                    # dv = [dist to neighbor + neighbor's dist to port, neighbor's port]
                    self.dv[port] = [c + dist, addr[1]]
                    updated = True

        if updated or not self.sent:
            self.sent = True
            self.print_routing()
            self.dv_broadcast()

    def print_routing(self):
        ts = str(time.time()) #datetime.datetime.now().strftime("%m-%d-%Y %H:%M:%S")
        print("[" + ts + "]", "Node", self.port, "Routing Table")
        for port in self.dv:
            dist = self.dv[port][0]
            next_hop = self.dv[port][1]
            
            if next_hop and next_hop != int(port):
                msg = "- (" + str(dist) + ") -> Node " + str(port) + "; Next hop -> Node " + str(next_hop)
            else: 
                msg = "- (" + str(dist) + ") -> Node " + str(port)

            print(msg)

    def err_msg(self, msg):
        print(msg)
        sys.exit(1)

    def validate_port(self, port):
        if int(port) < 1024 or 65535 < int(port):
            self.err_msg("Port numbers must be in the range 1024-65535.")

node = RouteNode()
node.run()