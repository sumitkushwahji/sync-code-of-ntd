from socket import AF_INET, SOCK_DGRAM
import threading
import sys
import socket
import datetime
import binascii
import struct, time

NTD_IP = ["172.16.26.10"]
log_file = "other_log.csv"
global timestamp


class NTPException(Exception):
    pass


class NTP:
    _SYSTEM_EPOCH = datetime.date(*time.gmtime(0)[0:3])
    _NTP_EPOCH = datetime.date(1900, 1, 1)
    NTP_DELTA = (_SYSTEM_EPOCH - _NTP_EPOCH).days * 24 * 3600
    REF_ID_TABLE = {
        "GOES": "Geostationary Orbit Environment Satellite",
        "GPS\0": "Global Position System",
        "GAL\0": "Galileo Positioning System",
        "PPS\0": "Generic pulse-per-second",
        "IRIG": "Inter-Range Instrumentation Group",
        "WWVB": "LF Radio WWVB Ft. Collins, CO 60 kHz",
        "DCF\0": "LF Radio DCF77 Mainflingen, DE 77.5 kHz",
        "HBG\0": "LF Radio HBG Prangins, HB 75 kHz",
        "MSF\0": "LF Radio MSF Anthorn, UK 60 kHz",
        "JJY\0": "LF Radio JJY Fukushima, JP 40 kHz, Saga, JP 60 kHz",
        "LORC": "MF Radio LORAN C station, 100 kHz",
        "TDF\0": "MF Radio Allouis, FR 162 kHz",
        "CHU\0": "HF Radio CHU Ottawa, Ontario",
        "WWV\0": "HF Radio WWV Ft. Collins, CO",
        "WWVH": "HF Radio WWVH Kauai, HI",
        "NIST": "NIST telephone modem",
        "ACTS": "NIST telephone modem",
        "USNO": "USNO telephone modem",
        "PTB\0": "European telephone modem",
        "LOCL": "uncalibrated local clock",
        "CESM": "calibrated Cesium clock",
        "RBDM": "calibrated Rubidium clock",
        "OMEG": "OMEGA radionavigation system",
        "DCN\0": "DCN routing protocol",
        "TSP\0": "TSP time protocol",
        "DTS\0": "Digital Time Service",
        "ATOM": "Atomic clock (calibrated)",
        "VLF\0": "VLF radio (OMEGA,, etc.)",
        "1PPS": "External 1 PPS input",
        "FREE": "(Internal clock)",
        "INIT": "(Initialization)",
        "\0\0\0\0": "NULL",
    }
    STRATUM_TABLE = {
        0: "unspecified or invalid",
        1: "primary reference (%s)",
    }
    MODE_TABLE = {
        0: "reserved",
        1: "symmetric active",
        2: "symmetric passive",
        3: "client",
        4: "server",
        5: "broadcast",
        6: "reserved for NTP control messages",
        7: "reserved for private use",
    }
    LEAP_TABLE = {
        0: "no warning",
        1: "last minute of the day has 61 seconds",
        2: "last minute of the day has 59 seconds",
        3: "unknown (clock unsynchronized)",
    }


class NTPPacket:
    _PACKET_FORMAT = "!B B B b 11I"

    def __init__(self, version=2, mode=3, tx_timestamp=0):
        self.leap = 0
        self.version = version
        self.mode = mode
        self.stratum = 0
        self.poll = 0
        self.precision = 0
        self.root_delay = 0
        self.root_dispersion = 0
        self.ref_id = 0
        self.ref_timestamp = 0
        self.orig_timestamp = 0
        self.recv_timestamp = 0
        self.tx_timestamp = tx_timestamp

    def to_data(self):
        try:
            packed = struct.pack(
                NTPPacket._PACKET_FORMAT,
                (self.leap << 6 | self.version << 3 | self.mode),
                self.stratum,
                self.poll,
                self.precision,
                _to_int(self.root_delay) << 16 | _to_frac(self.root_delay, 16),
                _to_int(self.root_dispersion) << 16
                | _to_frac(self.root_dispersion, 16),
                self.ref_id,
                _to_int(self.ref_timestamp),
                _to_frac(self.ref_timestamp),
                _to_int(self.orig_timestamp),
                _to_frac(self.orig_timestamp),
                _to_int(self.recv_timestamp),
                _to_frac(self.recv_timestamp),
                _to_int(self.tx_timestamp),
                _to_frac(self.tx_timestamp),
            )
        except struct.error:
            raise NTPException("Invalid NTP packet fields.")
        return packed

        try:
            unpacked = struct.unpack(
                NTPPacket._PACKET_FORMAT,
                data[0 : struct.calcsize(NTPPacket._PACKET_FORMAT)],
            )
        except struct.error:
            raise NTPException("Invalid NTP packet.")
        self.leap = unpacked[0] >> 6 & 0x3
        self.version = unpacked[0] >> 3 & 0x7
        self.mode = unpacked[0] & 0x7
        self.stratum = unpacked[1]
        self.poll = unpacked[2]
        self.precision = unpacked[3]
        self.root_delay = float(unpacked[4]) / 2**16
        self.root_dispersion = float(unpacked[5]) / 2**16
        self.ref_id = unpacked[6]
        self.ref_timestamp = _to_time(unpacked[7], unpacked[8])
        self.orig_timestamp = _to_time(unpacked[9], unpacked[10])
        self.recv_timestamp = _to_time(unpacked[11], unpacked[12])
        self.tx_timestamp = _to_time(unpacked[13], unpacked[14])


class NTPStats(NTPPacket):
    def __init__(self):
        NTPPacket.__init__(self)
        self.dest_timestamp = 0

    def from_data(self, data):
        try:
            unpacked = struct.unpack(
                NTPPacket._PACKET_FORMAT,
                data[0 : struct.calcsize(NTPPacket._PACKET_FORMAT)],
            )
        except struct.error:
            raise NTPException("Invalid NTP packet.")
        self.leap = unpacked[0] >> 6 & 0x3
        self.version = unpacked[0] >> 3 & 0x7
        self.mode = unpacked[0] & 0x7
        self.stratum = unpacked[1]
        self.poll = unpacked[2]
        self.precision = unpacked[3]
        self.root_delay = float(unpacked[4]) / 2**16
        self.root_dispersion = float(unpacked[5]) / 2**16
        self.ref_id = unpacked[6]
        self.ref_timestamp = _to_time(unpacked[7], unpacked[8])
        self.orig_timestamp = _to_time(unpacked[9], unpacked[10])
        self.recv_timestamp = _to_time(unpacked[11], unpacked[12])
        self.tx_timestamp = _to_time(unpacked[13], unpacked[14])

    @property
    def offset(self):
        return (
            (self.recv_timestamp - self.orig_timestamp)
            + (self.tx_timestamp - self.dest_timestamp)
        ) / 2

    @property
    def delay(self):
        return (self.dest_timestamp - self.orig_timestamp) - (
            self.tx_timestamp - self.recv_timestamp
        )

    @property
    def tx_time(self):
        return ntp_to_system_time(self.tx_timestamp)

    @property
    def recv_time(self):
        return ntp_to_system_time(self.recv_timestamp)

    @property
    def orig_time(self):
        return ntp_to_system_time(self.orig_timestamp)

    @property
    def ref_time(self):
        return ntp_to_system_time(self.ref_timestamp)

    @property
    def dest_time(self):
        return ntp_to_system_time(self.dest_timestamp)


class NTPClient:
    def __init__(self):
        pass

    def request(self, host, version=2, port="ntp", timeout=5):
        addrinfo = socket.getaddrinfo(host, port)[0]
        family, sockaddr = addrinfo[0], addrinfo[4]
        s = socket.socket(family, socket.SOCK_DGRAM)

        try:
            s.settimeout(timeout)
            query_packet = NTPPacket(
                mode=3, version=version, tx_timestamp=system_to_ntp_time(time.time())
            )
            s.sendto(query_packet.to_data(), sockaddr)
            src_addr = (None,)
            while src_addr[0] != sockaddr[0]:
                response_packet, src_addr = s.recvfrom(256)
            dest_timestamp = system_to_ntp_time(time.time())
        except socket.timeout:
            raise NTPException("No response received from %s." % host)
        finally:
            s.close()

        stats = NTPStats()
        stats.from_data(response_packet)
        stats.dest_timestamp = dest_timestamp

        return stats


def _to_int(timestamp):
    return int(timestamp)


def _to_frac(timestamp, n=32):
    return int(abs(timestamp - _to_int(timestamp)) * 2**n)


def _to_time(integ, frac, n=32):
    return integ + float(frac) / 2**n


def ntp_to_system_time(timestamp):
    return timestamp - NTP.NTP_DELTA


def system_to_ntp_time(timestamp):
    """Convert a system time to a NTP time.

    Parameters:
    timestamp -- timestamp in system time

    Returns:
    corresponding NTP time
    """
    return timestamp + NTP.NTP_DELTA


def leap_to_text(leap):
    if leap in NTP.LEAP_TABLE:
        return NTP.LEAP_TABLE[leap]
    else:
        raise NTPException("Invalid leap indicator.")


def mode_to_text(mode):
    if mode in NTP.MODE_TABLE:
        return NTP.MODE_TABLE[mode]
    else:
        raise NTPException("Invalid mode.")


def stratum_to_text(stratum):
    if stratum in NTP.STRATUM_TABLE:
        return NTP.STRATUM_TABLE[stratum] % (stratum)
    elif 1 < stratum < 16:
        return "secondary reference (%s)" % (stratum)
    elif stratum == 16:
        return "unsynchronized (%s)" % (stratum)
    else:
        raise NTPException("Invalid stratum or reserved.")


def ref_id_to_text(ref_id, stratum=2):
    fields = (
        ref_id >> 24 & 0xFF,
        ref_id >> 16 & 0xFF,
        ref_id >> 8 & 0xFF,
        ref_id & 0xFF,
    )

    if 0 <= stratum <= 1:
        text = "%c%c%c%c" % fields
        if text in NTP.REF_ID_TABLE:
            return NTP.REF_ID_TABLE[text]
        else:
            return "Unidentified reference source '%s'" % (text)
    elif 2 <= stratum < 255:
        return "%d.%d.%d.%d" % fields
    else:
        raise NTPException("Invalid stratum.")


def get_ntp_time(host):
    port = 123
    # Port.
    read_buffer = 1024
    # The size of the buffer to read in the received UDP packet.
    address = (host, port)
    # Tuple needed by sendto.
    data = "\x1b" + 47 * "\0"
    # Hex message to send to the server.

    epoch = 2208988800
    # Time in seconds since Jan, 1970 for UNIX epoch.

    client = socket.socket(AF_INET, SOCK_DGRAM)
    # Internet, UDP

    client.sendto(data, address)
    # Aend the UDP packet to the server on the port.

    data, address = client.recvfrom(read_buffer)
    # Get the response and put it in data and put the send socket address into address.

    t = struct.unpack("!12I", data)[10]
    # Unpack the binary data and get the seconds out.

    return t - epoch
    # Calculate seconds since the epoch.


def send_time(host, data, server):
    global open_ntd_count, timestamp, var_log_file

    host_ip, server_port = host, 10000
    tcp_client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        tcp_client.connect((host_ip, server_port))
        tcp_client.sendall(data)
        received = tcp_client.recv(1024)
        var_log_file.write(
            str(datetime.datetime.now())
            + ","
            + time.ctime(timestamp - bias)
            + ","
            + host
            + ",Synchronized"
            + ","
            + str(bias)
            + "\r\n"
        )
    except Exception as e:
        var_log_file.write(
            str(datetime.datetime.now())
            + ","
            + time.ctime(timestamp - bias)
            + ","
            + host
            + ",Not Connected"
            + ","
            + str(bias)
            + ","
            + str(e)
            + "\r\n"
        )
    finally:
        open_ntd_count -= 1
        tcp_client.close()


def sync_ntd(server, hosts):
    global open_ntd_count, timestamp, var_log_file

    print("Please wait while getting time from", server, "\r\n")
    try:
        response = call.request(server, version=3)
        timestamp = round(response.tx_time + bias)
        print("NPLI NTP TIME:", time.ctime(timestamp), "\r\n")
        ntp_date = datetime.datetime.fromtimestamp(timestamp)
        header = b"\x55\xaa\x00\x00\x01\x01\x00\xc1\x00\x00\x00\x00\x00\x00\x0f\x00\x00\x00\x0f\x00\x10\x00\x00\x00\x00\x00\x00\x00"
        footer = b"\x00\x00\x0d\x0a"
        year1 = bytes([ntp_date.year // 256])
        year2 = bytes([ntp_date.year % 256])
        data = (
            header
            + year2
            + year1
            + bytes([ntp_date.month])
            + bytes([ntp_date.day])
            + bytes([ntp_date.hour])
            + bytes([ntp_date.minute])
            + bytes([ntp_date.second])
            + footer
        )

        for host in hosts:
            open_ntd_count += 1
            threading.Thread(target=send_time, args=(host, data, server)).start()
    except Exception as e:
        var_log_file.write(
            str(datetime.datetime.now())
            + ","
            + "Failed to get NTP time"
            + ","
            + str(e)
            + "\r\n"
        )


def loop():
    global open_ntd_count, var_log_file
    while True:
        var_log_file = open(log_file, "a")
        open_ntd_count = 0

        sync_ntd(ntp_server_name, NTD_IP)
        while open_ntd_count > 0:
            continue
        var_log_file.close()

        time.sleep(sync_time)


def start():
    global ntp_server_name, call, bias, sync_time
    ntp_server_name = input("Server: ")

    sync_time = 60 * int(input("Schedule Synchronization time (in minutes): "))

    bias = int(input("Bias (in Seconds): "))
    call = NTPClient()
    print("Synchronising NTD:-\n")
    for host in NTD_IP:
        print(host + "\n")

    try:
        loop()
    except Exception as e:
        print(e)
        print("Alert: unable to get NTP Time...")
        time.sleep(60)
        print("RESTARTING...")
        loop()


start()

# Abha Ghildiyal edited this code
# Making changes to the code
