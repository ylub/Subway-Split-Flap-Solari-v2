sf.plugins.lirr = {
  dataType: 'json',

  url: function(options) {
    const feed = encodeURIComponent($('#feed-select').val() || 'lirr');
    const station = encodeURIComponent($('#station-input').val() || 'Jamaica');
    return '/api/departures?feed=' + feed + '&station=' + station + '&limit=' + (options.maxResults || 12);
  },

  formatData: function(response) {
    const feedKey = response.feed && response.feed.key ? response.feed.key : 'lirr';

    if (response.feed && response.feed.label) {
      $('#feed-title').text(response.feed.label);
    }
    if (response.station && response.station.stop_name) {
      $('#station-title').text(response.station.stop_name);
    }

    return (response.departures || []).map(function(item) {
      const routeSymbol = item.route_symbol || item.route_id || item.route_name;
      const subwayFeed = feedKey === 'subway' || feedKey === 'subway_supplemented';
      const express = subwayFeed && isExpressRoute(routeSymbol);

      return {
        linecolor: item.route_color,
        line_text_color: item.route_text_color,
        line_symbol: shorten(routeSymbol, 7),
        line_symbol_display: shorten(express ? routeSymbol.replace(/X$/i, '') : routeSymbol, 7),
        line_express: express,
        feed_key: feedKey,
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

function paintLineBadges(rows, data) {
  rows.each(function(index, row) {
    const item = data[index] || {};
    const badge = $(row).find('.line-swatch');
    badge.css({
      background: item.linecolor || '#333333',
      color: item.line_text_color || '#ffffff'
    });
    badge.toggleClass('subway-symbol', item.feed_key === 'subway' || item.feed_key === 'subway_supplemented');
    badge.toggleClass('express-symbol', Boolean(item.line_express));
    badge.empty().append($('<span class="line-symbol-label"></span>').text(item.line_symbol_display || item.line_symbol || ''));
  });
}

$(document).on('sf:rows-loaded', function(event, rows, data) {
  paintLineBadges(rows, data);
});

function shorten(value, max) {
  const text = String(value || '').toUpperCase();
  return text.length > max ? text.slice(0, max - 1) + '.' : text;
}

function isExpressRoute(value) {
  return /^[A-Z0-9]+X$/i.test(String(value || ''));
}

$(document).on('submit', '#station-form', function(event) {
  event.preventDefault();
  const url = new URL(window.location);
  url.searchParams.set('feed', $('#feed-select').val() || 'lirr');
  url.searchParams.set('station', $('#station-input').val() || 'Jamaica');
  history.replaceState(null, '', url);
  items.url = sf.plugins.lirr.url(sf.options);
  items.update(sf.options);
});
