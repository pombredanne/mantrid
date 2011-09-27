import json
import re


class HttpNotFound(Exception):
    "Exception raised to pass on a 404 error."
    pass


class HttpMethodNotAllowed(Exception):
    "Exception raised for a valid path but invalid method."
    pass


class HttpBadRequest(Exception):
    "Exception raised for an invalidly formed host entry."
    pass


class ManagementApp(object):
    """
    Management WSGI app for the Mantrid loadbalancer.
    Allows endpoints to be changed via HTTP requests to
    the management port.
    """

    host_regex = re.compile(r"^/host/([^/]+)/?$")

    def __init__(self, balancer):
        self.balancer = balancer

    def handle(self, environ, start_response):
        "Main entry point"
        # Pass off to the router
        try:
            handler = self.route(
                environ['PATH_INFO'].lower(),
                environ['REQUEST_METHOD'].lower(),
            )
            if handler is None:
                raise HttpNotFound()
        # Handle errors
        except HttpNotFound:
            start_response('404 Not Found', [('Content-Type', 'application/json')])
            return [json.dumps({"error": "not_found"})]
        except HttpMethodNotAllowed:
            start_response('405 Method Not Allowed', [('Content-Type', 'application/json')])
            return [json.dumps({"error": "method_not_allowed"})]
        # Dispatch to the named method
        body = environ['wsgi.input'].read()
        if body:
            body = json.loads(body)
        response = handler(
            environ['PATH_INFO'].lower(),
            body,
        )
        # Send the response
        start_response('200 OK', [('Content-Type', 'application/json')])
        return [json.dumps(response)]

    def route(self, path, method):
        # Simple routing for paths
        if path == "/":
            if method == "get":
                return self.get_all
            elif method == "put":
                return self.set_all
            else:
                raise HttpMethodNotAllowed()
        elif self.host_regex.match(path):
            if method == "get":
                return self.get_single
            if method == "put":
                return self.set_single
            else:
                raise HttpMethodNotAllowed()
        else:
            raise HttpNotFound()

    ### Handling methods ###

    def host_errors(self, hostname, details):
        """
        Validates the format of a host entry
        Returns an error string, or None if it is valid.
        """
        if not hostname or not isinstance(hostname, basestring):
            return "hostname_invalid"
        if not isinstance(details, list):
            return "host_details_not_list"
        if len(details) != 3:
            return "host_details_wrong_length"
        if not details[0] not in self.balancer.action_mapping:
            return "host_action_invalid"
        if not isinstance(details[1], dict):
            return "host_kwargs_not_dict"
        if not isinstance(details[2], bool):
            return "host_match_subdomains_not_bool"
        return None

    def get_all(self, path, body):
        return self.balancer.hosts

    def set_all(self, path, body):
        "Replaces the hosts list with the provided input"
        # Do some error checking
        if not isinstance(body, dict):
            raise HttpBadRequest("body_not_a_dict")
        for hostname, details in body.items():
            error = self.host_errors(hostname, details)
            if error:
                raise HttpBadRequest("%s:%s" % (hostname, error))
        # Replace
        self.balancer.hosts = body
        return {"ok": True}

    def get_single(self, path, body):
        host = self.host_regex.match(path).group(1)
        if host in self.balancer.hosts:
            return self.balancer.hosts[host]
        else:
            return None

    def set_single(self, path, body):
        host = self.host_regex.match(path).group(1)
        error = self.host_errors(host, body)
        if error:
            raise HttpBadRequest("%s:%s" % (host, error))
        self.balancer.hosts[host] = body
        return {"ok": True}