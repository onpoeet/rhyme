import sys
import os
import time
import subprocess
import signal
import psutil
import tempfile
import socket

from client import TimblClient

from timblexceptions import ConnectionError, ServerConnectionError


def pid_file(server):
    """
    Return the path to the file holding the pid for a given instance
    of TimblServer.

    Args:
        - server: an instance of Timblserver that needs to be started
    Returns:
        str -- the path to the file containing the pid for this server.
    """
    return os.path.join(
        tempfile.gettempdir(),
        'mbmp.%s_%s_%s.pid' % (server.classifier, server.port, server.host))


def remove_pid_file(server):
    """
    Remove the file holding the pid for a given instance of TimblServer.

    Args:
        - server: an instance of Timblserver that needs to be started
    Returns:
        boolean        
    """
    try:
        os.remove(pid_file(server))
    except OSError:
        pass


def free_port(server):
    """
    Utility function to check whether a given port is free.

    Args:
        - server: an instance of Timblserver that needs to be started
    Returns:
        boolean        
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((server.host, server.port))
        s.close()
        return False
    except socket.error, e:
        return True


def server_in_use(serverinstance):
    """
    Check if there are any other connections with the timblserver. If so,
    return True, else return False.

    Args:
        - server: an instance of Timblserver that needs to be started
    Returns:
        boolean
    """
    command = 'netstat -an | grep :%s' % serverinstance.port
    p = subprocess.Popen(command, shell=True, stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         close_fds=True)
    # count how many established connections there are
    established = sum(1 for line in p.stdout if 'ESTABLISHED' in line)
    if established > 1:
        return True
    return False

class TimblServer(object):
    """
    An interface to the TimblServer. The server can be questioned via
    the TimblClient. The host specifies the server address (localhost by
    default) and port specifies the server tcp communicating port. Features
    is a dictionary of flags and options send to the server. This can be
    specified in the config.py file.
    """

    def __init__(self, host='localhost', port=8080, features={}, classifier=None):
        """
        Constructor. Initializes a TimblServer

        Args:
            - host (str): Host specifies the server address (localhost by default)
            - port (int): Port specifies the server tcp communicating port.
            - features (dict): the settings used by Timbl (see :mod:`mbmp.config`)
        """
        self.host = host
        self.port = port
        self.process = 'timblserver'
        self.features = features
        self.classifier = classifier

    def _setup(self):
        """
        Return the commandlist send to the TimblServer.
        """
        command_list = [self.process]
        command_list.extend(
            ['-S', '%s' % self.port, '--pidfile=', pid_file(self)])
        for option, value in self.features.items():
            if not option.startswith(('-','+')):
                option = '-%s' % option
            command_list.extend([option, value])
        return command_list

    def started(self):
        """
        Return True if the server is started, False otherwise.
        """
        client = None
        try:
            client = TimblClient(port=self.port)
        except (ConnectionError, socket.error):
            del client
            return False
        return True

    def __repr__(self):
        return '<TimblServer host=%s, port=%s, process=%s>' % (
            self.host, self.port, self.process)

    def owns_server(self):
        """
        Return True if the timblserver is owned by the current user.
        """
        username = lambda pid: psutil.Process(pid).username
        return username(self.pid()) == username(os.getpid())

    def run(self):
        """
        Tries to start the TimblServer at the given host and port. If the
        server is already running, does nothing
        """
        if (self.started() and os.path.exists(pid_file(self)) and
            self.owns_server()):
            sys.stderr.write('Server already running at %s:%s\n' % (
                self.host, self.port))
            return True
        if not free_port(self):
            raise ServerConnectionError(
                'Other process running at %s:%s. Specify another port' % (
                    self.host, self.port))
        out = open(os.devnull, 'w')
        self._process = subprocess.Popen(
            self._setup(), stderr=out, stdout=out)
        sys.stderr.write('Starting server at %s:%s' % (self.host, self.port))
        while not self.started():
            time.sleep(1.0)
            sys.stderr.write('.')
        sys.stderr.write(
            '\nServer up and running at %s:%s\n' % (self.host, self.port))
        return True

    def pid(self):
        """
        Return the pid of the timblserver associated with this
        instance of the class TimblServer. If no file is found, return None.
        """
        try:
            with open(pid_file(self)) as pidfile:
                return int(pidfile.read().strip())
        except IOError:
            return None

    def kill(self):
        """
        Kill the TimblServer. Return True if the server is killed,
        false otherwise.
        """
        pid = self.pid()
        remove_pid_file(self)
        if not self.started():
            return True
        if pid is not None:
            os.kill(pid, signal.SIGTERM)
            time.sleep(0.1)
            self._process = None
            sys.stderr.write(
                'TimblServer at %s:%s killed...\n' % (self.host, self.port))
            return True
        return False