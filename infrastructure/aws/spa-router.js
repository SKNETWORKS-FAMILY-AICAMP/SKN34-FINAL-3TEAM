function handler(event) {
  var request = event.request;
  var uri = request.uri;
  if (uri === '/api' || uri.indexOf('/internal') === 0 || uri.indexOf('/actuator') === 0) {
    return {statusCode: 404, statusDescription: 'Not Found', headers: {'cache-control': {value: 'no-store'}}};
  }
  if (uri.indexOf('.') === -1) request.uri = '/index.html';
  return request;
}
