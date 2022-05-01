import sys
import socket
import json
import time
import datetime
import threading
import math

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
            if mode == "r" or mode == "p":
                self.mode = mode
                self.distance_vector()
            else:
                self.err_msg("Usage: Mode must be 'r' (regular) or 'p' (poisoned reverse)")
        else:
            self.err_msg("Usage: Algorithm must be 'dv' or ... ")

    def distance_vector(self):
        sock.bind((self.ip, self.port))    # socket listening
        if self.last:
            self.sent = True
            self.dv_broadcast()
            t = threading.Timer(2, self.send_cost_change)
            t.start()

        recv_th = threading.Thread(target=self.dv_recv)
        recv_th.start()
    
    def send_cost_change(self):
        highest_port = max(self.dv)
        self.neighbors[highest_port] = self.cost_change

        self.dv[highest_port][0] = self.cost_change
        ts = str(time.time())
        print("[" + ts + "]", "Node", highest_port, "cost updated to", self.cost_change)
        
        msg = ("COS\n" + str(self.cost_change) + "\n").encode()
        sock.sendto(msg, (self.ip, highest_port))
        print("[" + ts + "]", "Link value message sent from Node", self.port, "to Node", highest_port)

    def dv_broadcast(self, poison=False):
        send_dv = self.dv.copy()
        table = b"TAB\n" + json.dumps(send_dv).encode() + b"\n"
        self.sent = True

        for n in self.neighbors:  
            if poison:
                send_dv = self.dv.copy()
                for port in self.dv:
                    # if next hop to port is through n, poison the path back
                    if port != n and self.dv[port][1] == n:
                        send_dv[port][0] = math.inf

                table = b"TAB\n" + json.dumps(send_dv).encode() + b"\n"

            print("Message sent from Node", self.port, "to Node", n)
            print("  ", send_dv)
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
                    print(self.most_recent)
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

        # if sender is an immediate neighbor
        if self.dv[sender][1] == sender:
            for port in self.most_recent:
                if port != sender:
                    # if most recent table received says there's a shorter way to Y, loop through most recent tables received
                    table = self.most_recent[port]

                    # most recent distance of neighbor to update sender + distance to neighbor
                    alt_dist = table[str(sender)][0] + self.dv[port][0]
                    if alt_dist < cost:
                        self.dv[sender] = [alt_dist, port]
                        updated = True
                        print('cost updated', self.dv[sender])
                    else: 
                        self.dv[sender] = [cost, sender]
                        updated = True

        if updated:
            self.dv_broadcast(poison=(self.mode == "p"))
            print("broadcast from cost update")
            self.print_routing()
        return updated
            
    # Compute to change own DV based off table from addr
    def dv_compute(self, table, addr):
        sender = addr[1]
        c = self.dv[sender][0]  # distance between neighbor port and selfs
        updated = False
        print("  Received table from", addr,":",table)

        for port in table:
            dist = c + table[port][0]
            port = int(port)
            
            if port != self.port:
                # if distance to port in new table is unknown
                if port not in self.dv:
                    self.dv[port] = [dist, sender]  # s[dist to neighbor + neighbor's dist to port, neighbor's port]
                    print("broadcast because port not in dv")
                    updated = True

                # if a former path to the node is known
                elif port in self.dv:
                    # If direct path is shortest
                    if self.neighbors[port] < dist and self.neighbors[port] < self.dv[port][0]:
                        self.dv[port] = [self.neighbors[port], port]
                        updated = True

                    # If a shorter non-direct path is found
                    if dist < self.dv[port][0]: 
                        next_hop = self.dv[sender][1]   # next hop to get to sender
                        self.dv[port] = [dist, next_hop]
                        print("broadcast bc shorter path found")
                        updated = True

                    # if the former shortest path got longer: the sender == next hop for a port in the table
                    elif dist > self.dv[port][0] and sender == self.dv[port][1]:
                        print("neighbor cost", self.neighbors[port], "neighbor port", port)
                        if dist < self.neighbors[port]:
                            self.dv[port] = [dist, sender] 
                        else:
                            self.dv[port] = [self.neighbors[port], port]
                        print("broadcast because shortest path got longer")
                        updated = True

                    # sending node routes through receiver to get to a diff node
                    '''elif table[str(port)][1] == self.port:
                        self.dv_broadcast(dest=port, poison=True)'''

        if updated or not self.sent:
            self.sent = True
            self.print_routing()
            self.dv_broadcast(poison=(self.mode == "p"))
        return updated

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