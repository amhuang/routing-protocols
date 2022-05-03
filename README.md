# Routing Protocols Implementation

Name: Andrea Huang

UNI: amh2341

The file contains the project documentation, program features, usage scenarios, brief explanation of algorithms or data structures used, and the description of any additional features/functions you implemented. This should be a text file. You will lose points if you submit a PDF, .rtf, or any other format.

## Usage

## Implementation Overview

`routenode.py` creates a `RouteNode` object which `run()` is called on to process command line arguments and run the algorithm specified.

`RouteNode` uses the following data structures:
- `self.neighbors` : A dictionary that holds the node's neighbors and the costs to them in the format `{port: cost, ... }`
- `self.routing`: A dictionary which holds a routing table for the link state algorithm and a distance vector for the distance vector algorithm. Format: `{port: [cost, next_hop], ... }`
- `self.most_recent`: A dictionary that holds the last distance vector received from each port. Used only in with the distance vector algorithm. Format: `{port: dv dictionary (in the format of self.routing), ... }`
- `self.topology`: A dictionary which stores the topology of graph with link as keys and costs as values. Used only with the link state algorithm. Format { (lower_port, higher_port) : cost, ... }
- `self.recvd`: A dictionary which keeps track of LSAs received in order to check for duplicates. Format: `{seq num: origin port, ... }`


## Distance Vector Implementation

The function `distance_vector()` initializes the distance vector algorithm. The initial distance vector is just the node's neighbors and their respective costs. If the node is provided the `last` argument, the

**Protocol**

The protocol for a cost change command is a message preceded by the header `COS`, separated from the cost with `\n`. Distance vectors are sent with the header preceded by the header `TAB`, separated from the table (sent as a JSON) with `\n`.


**Program Structure**

The distance vector algorithm is implemented with a multi-threading approach, with one thread responosible for receiving messages and the other responsible for sending out the initial distance vector from the `last` node. One threaded Timer delays the cost change by 30 second (hard coded).

**Poisoned Reverse**

In poisoned reverse mode, `dv_broadcast()`, the function that broadcasts a node's distance vector to its neighbors, does so by first looping through each neighbor. It makes a separate copy of the local distance vector for each neighbor. It loops through all the ports in its distance vector for each neighbor and identifies if the port is the next hop for each port (excluding the neighbor itself). If it is, it makes the distance to that port infinity to poison the path so it doesn't loop back on itself. Thus, the distance vectors sent to each neighbor will differ.

**Compute Distance Vector** 

The function `dv_compute(table, addr)` computes the node's new distance vector off of the `table` (same format as a distance vector) received from `addr`. 

It does so by looping through all the ports in `table` and applying the Bellman-Ford equation. If the port isn't in the distance vector, it adds it with the distance provided from `table` plus the distance of from the node to the sender with the address `addr`. Let this distance be `c` 

If the local distance vector has a former path to the port, it checks 3 conditions: if a direct path between the port and the receiving node is the shortest path, if a shorter non-direct path is found (with the Bellman-Ford equation), and if the former shortest path got longer due to a cost update (i.e. the sender `addr` is the next hop for a port in the distance vector).

**Cost Update**

When the cost update occurs, `send_cost_change()` (the same function called by the distance vector), a cost update command message is sent to the node on the other end of the link (neighbor with the highest port). The routing table is updated so that the cost to the neighbor with the highest port number is updated. 

The receiver of a cost change message calls `recv_cost_change()`, which then calls `dv_cost_update(sender, cost)`. This looks at the most recent distance vectors sent from each port stored in `self.most_recent` and sees if there's a shorter path through one of those rather than through the path it currently has in its distance vector.


## Link State Implementation

**Protocol**

The protocol for a cost change command is a message with the header `COS`, separated from the cost with `\n`. The LSA and sequence number of the most recent LSA are stored as object variables. The LSA is sent with the header `LSA`, separated from the body by `\n`. The rest of the data fields are also separated by `\n` and are listed in the following order: the origin node's port, the origin node's neighbors and costs, and the sequence number. The sequence number is a time stamp rounded to 3 decimal places. 

**Program Structure**

The link state algorithm is implemented with a multi-threading approach, with one thread responosible for receiving messages and the other responsible for sending out the initial LSA from the `last` node. Two threaded Timers delay the computation of the routing table by `ROUTING_INTERVAL` and the cost change by `ROUTING_INTERVAL * 1.2`. A separate thread is reponsible for continuousy sending out the node's LSA every `update_interval`. 


**Flooding Mechanism & Duplicate LSAs**

The flooding mechanism is made more efficient by only forwarding LSAs that the node hasn't already forwarded. All LSAs that the node receives are stored in `self.recvd` with the sequence number as the key and the origin port as the value. The sequence number and origin ports of LSAs that are received are checked against `self.recvd`. If those two values are not in `self.recvd`, then the LSA gets forwarded to the node's neighbors. Otherwise, the packet gets dropped by not being forwarded. 

**Cost Update**

When the cost update occurs, `send_cost_change()` (the same function called by the distance vector) the node creates a new LSA with the updated costs of getting to its neighbors. A cost update command message is sent to the node on the other end of the link. The local record of the network topology is updated, and the routing table is recomputed.

The receiver of a cost change message calls `recv_cost_change()`, which similarly makes a new LSA, updates the topology, and recomputes the routing table at the receiving node. The receiving node broadcasts its new LSA to its neighbors.

## Tests

I tested all the required functionalities and error catching to the best of my ablities, and I have not found any bugs. 

The text output for tests are provided in the specs are provided in `test.txt`. 

### Distance Vector Algorithm Tests

Tests 1-3 are provided from the specs. Tests 4-5 are my own and test a network with a count-to-infinity problem in regular and poisoned reverse mode.

**Test 1: Regular DV (from specs)**
```
python3 routenode.py dv r [any-num] 1111 2222 1 3333 50
python3 routenode.py dv r [any-num] 2222 1111 1 3333 2 4444 8
python3 routenode.py dv r [any-num] 3333 1111 50 2222 2 4444 5
python3 routenode.py dv r [any-num] 4444 2222 8 3333 5 last
```

**Test 2: DV with count-to-infinity problem in regular mode (from specs)**
```
python3 routenode.py dv r [any-num] 1111 2222 1 3333 50
python3 routenode.py dv r [any-num] 2222 1111 1 3333 2
python3 routenode.py dv r [any-num] 3333 1111 50 2222 2 last 60
```

**Test 3: Test 2 with poisoned reverse (from specs)**
```
python3 routenode.py dv p [any-num] 1111 2222 1 3333 50
python3 routenode.py dv p [any-num] 2222 1111 1 3333 2
python3 routenode.py dv p [any-num] 3333 1111 50 2222 2 last 60
```

**Test 4: DV with count-to-infinity problem.**
```
python3 routenode.py dv r [any-num] 1111 2222 2 3333 20
python3 routenode.py dv r [any-num] 2222 1111 2 3333 2
python3 routenode.py dv r [any-num] 3333 1111 20 2222 2 last 25
```

**Test 5: Test 4 with poisoned reverse.**
```
python3 routenode.py dv p [any-num] 1111 2222 2 3333 20
python3 routenode.py dv p [any-num] 2222 1111 2 3333 2
python3 routenode.py dv p [any-num] 3333 1111 20 2222 2 last 25
```

### Link State Algorithm Tests

Tests 1-2 are from the specs.

**Test 1: Regular LS algorithm (from specs)**
```
python3 routenode.py ls r 30 1111 2222 1 3333 50
python3 routenode.py ls r 30 2222 1111 1 3333 2 4444 8
python3 routenode.py ls r 30 3333 1111 50 2222 2 4444 5
python3 routenode.py ls r 30 4444 2222 8 3333 5 last
```
**Test 2: LS algorithm with cost change (from specs)**
```
python3 routenode.py ls r 30 1111 2222 1 3333 50
python3 routenode.py ls r 30 2222 1111 1 3333 2
python3 routenode.py ls r 30 3333 1111 50 2222 2 last 60
```

**Test 3: LS algorithm with cost change (from specs)**
```
python3 routenode.py dv r 30 1111 2222 1 3333 20
python3 routenode.py dv r 30 2222 1111 1 3333 4 4444 2
python3 routenode.py dv r 30 3333 1111 20 2222 4 4444 2
python3 routenode.py dv r 30 4444 2222 2 3333 2 last 30
```