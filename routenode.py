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
        self.dv = {}            # distance vector in format { port : [cost, next_hop] }
        self.most_recent = {}

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
            self.cost_change = int(sys.argv[i])
        
        # run distance vector algorithm
        if algo == "dv":
            if mode == "r":
                self.distance_vector()  # run normal distance vector
            elif mode == "p":
                self.distance_vector(True)                    # run poisoned reverse
            else:
                self.err_msg("Usage: Mode must be 'r' (regular) or 'p' (poisoned reverse)")
        else:
            self.err_msg("Usage: Algorithm must be 'dv' or ... ")

    def distance_vector(self, poison=False):
        sock.bind((self.ip, self.port))    # socket listening
        if self.last:
            self.sent = True
            self.dv_broadcast()
            t = threading.Timer(3.0, self.send_poison)
            t.start()

        recv_th = threading.Thread(target=self.dv_recv)
        recv_th.start()
    
    def send_poison(self):
        highest_port = max(self.dv)
        self.neighbors[highest_port] = self.cost_change

        self.dv[highest_port][0] = self.cost_change
        ts = str(time.time())
        print("[" + ts + "]", "Node", highest_port, "cost updated to", self.cost_change)
        
        msg = ("COS\n" + str(self.cost_change) + "\n").encode()
        sock.sendto(msg, (self.ip, highest_port))
        print("[" + ts + "]", "Link value message sent from Node", self.port, "to Node", highest_port)


    def dv_broadcast(self):
        table = b"TAB\n" + json.dumps(self.dv).encode() + b"\n"
        for n in self.neighbors:
            print("Message sent from Node", self.port, "to Node", n)
            sock.sendto(table, (self.ip, n))


    def dv_recv(self):
        while True:
            # Receives routing table from addr
            body, addr = sock.recvfrom(2048)
            body = body.decode().split("\n")

            i = 0
            while i < len(body):
                if body[i] == "TAB":
                    i += 1
                    table = json.loads(body[i])
                    self.dv_compute(table, addr)
                    self.most_recent[addr[1]] = table
                    print("Message received at Node", self.port, "from Node", addr[1])
                
                elif body[i] == "COS":  # Cost change control message
                    i += 1
                    sender = addr[1]
                    cost = int(body[i])
                    self.neighbors[sender] = cost

                    ts = str(time.time())
                    print("[" + ts + "]", "Node", sender, "cost updated to", cost)
                    print("[" + ts + "]", "Link value message received at Node", self.port, "from Node", sender)
        
                    self.cost_update(sender, cost) 
                i += 1

    def cost_update(self, sender, cost):
        # if the edge changed used to be part of the shortest path, change the distance vector
        updated = False
        if self.dv[sender][1] == sender:
            for port in self.most_recent:
                if port != sender:
                    # if most recent table received says there's a shorter way to Y
                    # loop through most recent tables received
                    table = self.most_recent[port]

                    # most recent distance of neighbor to update sender + distance to neighbor
                    alt_dist = table[str(sender)][0] + self.dv[port][0]
                    if alt_dist < cost:
                        self.dv[sender] = [alt_dist, port]
                        updated = True
                        print('cost updated', self.dv[sender])

        if updated:
            self.dv_broadcast()
            self.print_routing()
        return updated
            
    # Compute to change own DV based off table from addr
    def dv_compute(self, table, addr):
        # distance between neighbor port and self
        sender = addr[1]
        c = self.dv[sender][0]
        updated = False
        #print("received table from", addr,"\n",table)

        for port in table:
            # if distance to port in new table is unknown
            dist = c + table[port][0]
            port = int(port)

            if port != self.port:
                # if a former path to the node is known
                if port in self.dv:
                    # If a shorter path is found
                    if dist < self.dv[port][0]:
                        # next hop to get to sender
                        next_hop = self.dv[sender][1]
                        self.dv[port] = [dist, next_hop]
                        updated = True 

                    # if the former shortest path got longer: the sender == next hop for a port in the table
                    elif dist > self.dv[port][0] and sender == self.dv[port][1]:
                        self.dv[port][0] = dist if dist < self.neighbors[port] else self.neighbors[port]
                        updated = True
                    
                else:
                    # dv = [dist to neighbor + neighbor's dist to port, neighbor's port]
                    self.dv[port] = [dist, sender]
                    updated = True

        if updated or not self.sent:
            self.sent = True
            self.print_routing()
            self.dv_broadcast()

    def print_routing(self):
        ts = str(time.time())   #datetime.datetime.now().strftime("%m-%d-%Y %H:%M:%S")
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