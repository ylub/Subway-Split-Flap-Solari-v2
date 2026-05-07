sf.plugins.lirr = {
  dataType: 'json',

  url: function(options) {
    const station = encodeURIComponent($('#station-input').val() || 'Jamaica');
    return '/api/departures?station=' + station + '&limit=' + (options.maxResults || 12);
  },

  formatData: function(response) {
    if (response.station && response.station.stop_name) {
      $('#station-title').text(response.station.stop_name);
    }

    return (response.departures || []).map(function(item) {
      return {
        linecolor: item.route_color,
        branch: shorten(item.route_name.replace(' Branch', ''), 16),
        destination: shorten(item.destination, 16),
        scheduled: item.departure_time.replace(' AM', 'A').replace(' PM', 'P'),
        minutes: String(item.minutes),
        remarks: item.status === 'Scheduled' ? 'SCHEDULED' : item.status,
        status: item.status === 'Scheduled' ? 'A' : 'B'
      };
    });
  }
};

function shorten(value, max) {
  const text = String(value || '').toUpperCase();
  return text.length > max ? text.slice(0, max - 1) + '.' : text;
}

$(document).on('submit', '#station-form', function(event) {
  event.preventDefault();
  items.url = sf.plugins.lirr.url(sf.options);
  items.update(sf.options);
});
