// polyfill, see https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Date/now
if (!Date.now) {
    Date.now = function now() {
        return new Date().getTime()
    }
}

r.timetext = {
    _chunks: (function () {
        function P_(x, y) { return [x, y] }
        return [
            [60 * 60 * 24 * 365, P_('a year ago', '%(num)s years ago')],
            [60 * 60 * 24 * 30, P_('a month ago', '%(num)s months ago')],
            [60 * 60 * 24, P_('a day ago', '%(num)s days ago')],
            [60 * 60, P_('an hour ago', '%(num)s hours ago')],
            [60, P_('a minute ago', '%(num)s minutes ago')]
        ]
    })(),

    init: function () {
        this.refresh()
        // TODO: is it worth making this more dynamic and going below 1 minute?
        setInterval(this.refresh, 60000)
    },

    refresh: function () {
        var now = Date.now()

        $('time.live').each(function () {
            r.timetext.refreshOne(this, now)
        })
    },

    refreshOne: function (el, now) {
        if (!now)
            now = Date.now()

        var $el = $(el)
        var isoTimestamp = $el.attr('datetime')
        var timestamp = Date.parse(isoTimestamp)
        var age = (now - timestamp) / 1000
        var chunks = r.timetext._chunks
        var text = r._('less than a minute ago')

        $.each(r.timetext._chunks, function (ix, chunk) {
            var count = Math.floor(age / chunk[0])
            if (count != 0) {
                var keys = chunk[1]
                text = r.P_(keys[0], keys[1], count).format({num: count})
                return false
            }
        })

        $el.text(text)
    }
}

r.timetext.init()
