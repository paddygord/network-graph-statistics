#!/usr/bin/env python3

import sys
import re
import json
from si_prefix import si_parse

info_line_re = re.compile(
    r"(?P<state>\S{1,13})\s*"
    r"(?P<recv_q>\S+)\s+"
    r"(?P<send_q>\S+)\s+"
    r"(?P<local_addr>\S+)\s+"
    r"(?P<peer_addr>\S+)\s+"
    r"(users:\((?P<users>[^)]+)\)|)\s+"
)

details_line_re = re.compile(
    r"\s+"
    r"cubic wscale:(?P<cubic_wscale>\S+)\s+"
    r"rto:(?P<rto>\S+)\s+"
    r"rtt:(?P<rtt>\S+)\s+"
    r"(ato:(?P<ato>\S+)\s+|)"
    r"mss:(?P<mss>\S+)\s+"
    r"pmtu:(?P<pmtu>\S+)\s+"
    r"rcvmss:(?P<rcvmss>\S+)\s+"
    r"advmss:(?P<advmss>\S+)\s+"
    r"cwnd:(?P<cwnd>\S+)\s+"
    r"(ssthresh:(?P<ssthresh>\S+)\s+|)"
    r"(bytes_sent:(?P<bytes_sent>\S+)\s+|)"
    r"(bytes_acked:(?P<bytes_acked>\S+)\s+|)"
    r"(bytes_received:(?P<bytes_received>\S+)\s+|)"
    r"(segs_out:(?P<segs_out>\S+)\s+|)"
    r"(segs_in:(?P<segs_in>\S+)\s+|)"
    r"(data_segs_out:(?P<data_segs_out>\S+)\s+|)"
    r"(data_segs_in:(?P<data_segs_in>\S+)\s+|)"
    r"send (?P<send>\S+)\s+"
    r"(lastsnd:(?P<lastsnd>\S+)\s+|)"
    r"(lastrcv:(?P<lastrcv>\S+)\s+|)"
    r"(lastack:(?P<lastack>\S+)\s+|)"
    r"(pacing_rate (?P<pacing_rate>\S+)\s+|)"
    r"(delivery_rate (?P<delivery_rate>\S+)\s+|)"
    r"(delivered:(?P<delivered>\S+)\s+|)"
    r"(?P<app_limited>app_limited\s+|)"
    r"(busy:(?P<busy>\S+)\s+|)"
    r"(rwnd_limited:(?P<rwnd_limited>\S+)\s+|)"
    r"(sndbuf_limited:(?P<sndbuf_limited>\S+)\s+|)"
    r"(unacked:(?P<unacked>\S+)\s+|)"
    r"(retrans:(?P<retrans>\S+)\s+|)"
    r"(lost:(?P<lost>\S+)\s+|)"
    r"(rcv_rtt:(?P<rcv_rtt>\S+)\s+|)"
    r"rcv_space:(?P<rcv_space>\S+)\s+"
    r"rcv_ssthresh:(?P<rcv_ssthresh>\S+)\s+"
    r"(notsent:(?P<notsent>\S+)\s+|)"
    r"minrtt:(?P<minrtt>\S+)"
)

user_re = re.compile(
    r'"(?P<name>[^"]+)",pid=(?P<pid>\w+),fd=(?P<fd>\w+)'
)
def parse_info_line(info_line):
    parts = info_line.split(maxsplit=5)
    if not (5 <= len(parts) <= 6):
        print('failed to parse info_line, wrong number of whitespace breaks')
        print('>>' + info_line + '<<')
        sys.exit(1)
    state = parts[0]
    recv_q = int(parts[1])
    send_q = int(parts[2])
    local_addr = parts[3]
    peer_addr = parts[4]
    users = []
    if len(parts) == 6:
        users_str = parts[5]
        users_strs = (users_str[len('users:(('):-3]).split('),(')
        for user_str in users_strs:
            m = re.match(user_re, user_str)
            if not m:
                print('failed to parse user: {}'.format(user))
                sys.exit(1)
            md = m.groupdict()
            users.append({'name': md['name'], 'pid': int(md['pid']), 'fd': int(md['fd'])})
    return {
        'state': state,
        'recv_q': recv_q,
        'send_q': send_q,
        'local_addr': local_addr,
        'peer_addr': peer_addr,
        'users': users
    }

def parse_rtt(rtt_str):
    s = rtt_str.split('/')
    return {'rtt_avg': float(s[0]), 'rtt_std_dev': float(s[1])}
def parse_bps(bps_str):
    assert(bps_str.endswith('bps'))
    bps_str = bps_str.replace('K', 'k')
    return si_parse(bps_str[:-3])
def parse_address(addr_str):
    host, port = addr_str.rsplit(':', 1)
    return {'host': host, 'port': port}

def parse_details_line(details_line):
    details_m = re.match(details_line_re, details_line)
    if not details_m:
        print('failed to parse details line: {}'.format(details_line))
        sys.exit(1)
    return details_m.groupdict()

def parse(file):
    lines = file.readlines()
    connections = []
    for info_line, details_line in zip(lines[0::2], lines[1::2]):
        info = parse_info_line(info_line)
        details = parse_details_line(details_line)
        users = info['users']
        local_pid = None
        peer_pid = None
        if len(users) > 0:
            local_pid = users[0]['name']
        if len(users) > 1:
            peer_pid = users[1]['name']
        if len(users) > 2:
            print('warning: case not really handled with more than 2 users of a connection')
            sys.exit(1)
        local_addr = parse_address(info['local_addr'])
        peer_addr = parse_address(info['peer_addr'])
        rtt_avg = parse_rtt(details['rtt'])['rtt_avg']
        rtt_sd = parse_rtt(details['rtt'])['rtt_std_dev']
        send_bandwidth = parse_bps(details['send'])
        #this merges the two dictionaries into one
        connection = {**info, **details}
        connection['rtt_avg'] = rtt_avg
        connection['rtt_sd'] = rtt_sd
        connection['send_bandwidth'] = send_bandwidth
        connection['local_pid'] = local_pid
        connection['peer_pid'] = peer_pid
        connection['local_addr_parsed'] = local_addr
        connection['peer_addr_parsed'] = peer_addr
        connection['users'] = users
        connections.append(connection)
    return connections

def graph(connections):
    address_pid_map = {}
    for connection in connections:
        address_pid_map[connection['local_addr']] = connection['local_pid']
        if connection['peer_addr'] and connection['peer_pid']:
            address_pid_map[connection['peer_addr']] = connection['peer_pid']

    nodes = []
    edges = []
    for connection in connections:
        #smaller weight = further apart
        connection['weight'] = 1 / connection['rtt_avg']
        if not connection['users']:
            continue
        local_pid = address_pid_map[connection['local_addr']]
        if connection['peer_addr'] in address_pid_map:
            peer_pid = address_pid_map[connection['peer_addr']]
            edges.append({'source': str(local_pid), 'target': str(peer_pid), **connection})
            nodes.append({'id': str(peer_pid)})
        else:
            edges.append({'source': str(local_pid), 'target': connection['peer_addr'], **connection})
            nodes.append({'id': str(connection['peer_addr'])})
        nodes.append({'id': str(local_pid), **connection['users'][0]})

    json_graph = {'nodes': nodes, 'links': edges}
    return json_graph

def main():
    connections = parse(open('ss.txt', 'r'))
    json_graph = graph(connections)
    with open('data.json', 'w') as outfile:
        json.dump(json_graph, outfile)

if __name__ == '__main__':
    main()
