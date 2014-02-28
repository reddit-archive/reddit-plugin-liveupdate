r.liveupdate = {
    _pixelInterval: 10 * 60 * 1000,
    _favicon: 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAMAAAAoLQ9TAAAA/1BMVEUpLzY+PDpGSk5HR0dKTlNSW2VTXGVVXmdWWl5bYWZdZGtfanVfbHpgXVtianNjbXhkZWdkam1lcX1nc4BpdYJqa2xscHZucHJueYRvfoxwfIhxcG93e4B3h5h4iJh5ipt7gIB8ipl+fn6BgYGImKOJh4aKjY2Mna6NobSOn7CQo7iar8Wfnp2juM6lo6Gmuc6mu8moqaqsw9etwcmurq6vrauxyN2xyN+0s7K+u7m/1u7C2vPF3fbI4PrJ4fvJ4/7Ly8vPzMnP6P7S0tLT0c/W8P/Z19Xd9/7d+P7e3Nrw8PDz9vT69/T+EA/+MjD+pqT+srD+w8H+zsz+/v7///9fla50AAAAuElEQVR42l2P2RaBUBhGT0WZ54jIPM8h0zE7SBL97/8uYoXFvtwXe30fIn8ggn94i8XMGSkFQvmPwFXvwOe/OGyx3OJYF+OUq26LcS2LMs05Xj0bPY+QDFc6k1bOnRQ8PYLiKlXW4IlWptQ4QWlxCIZ+h7tuwFBME9RgAG5XE8zrDYBpWNEEfElY0RO7Aejvzrs+wIa1xFGmp7AuFoprmNLya4fC8aP9YT/iOeX9pS1Fg1GpbZ/74wFo2jf64C4agwAAAABJRU5ErkJggg==',

    init: function () {
        this.$listing = $('.liveupdate-listing')
        this.$table = this.$listing.find('table tbody')
        this.$statusField = this.$listing.find('tr.initial td')

        this.$listing.find('nav.nextprev').remove()
        $(window)
            .scroll($.proxy(this, '_loadMoreIfNearBottom'))
            .scroll()  // in case of a short page / tall window

        if (r.config.liveupdate_websocket) {
            this._websocket = new r.WebSocket(r.config.liveupdate_websocket)
            this._websocket.on({
                'connecting': this._onWebSocketConnecting,
                'connected': this._onWebSocketConnected,
                'disconnected': this._onWebSocketDisconnected,
                'reconnecting': this._onWebSocketReconnecting,
                'message:delete': this._onDelete,
                'message:strike': this._onStrike,
                'message:activity': this._onActivityUpdated,
                'message:refresh': this._onRefresh,
                'message:settings': this._onSettingsChanged,
                'message:update': this._onNewUpdate
            }, this)
            this._websocket.start()
        }

        Tinycon.setOptions({
            'background': '#ff4500'
        })
        Tinycon.setImage(this._favicon)

        $(document).on({
            'show': $.proxy(this, '_onPageVisible'),
            'hide': $.proxy(this, '_onPageHide')
        })
        this._onPageVisible()

        this._fetchPixel()
    },

    _onPageVisible: function () {
        if (this._needToFetchPixel) {
            this._fetchPixel()
        }

        this._pageVisible = true
        this._unreadUpdates = 0
        this._needToFetchPixel = false
        Tinycon.setBubble()
    },

    _onPageHide: function () {
        this._pageVisible = false
    },

    _onWebSocketConnecting: function () {
        this.$statusField.addClass('connecting')
                         .text(r._('connecting to update server...'))

        if (this._reconnectCountdown) {
            this._reconnectCountdown.cancel()
        }
    },

    _onWebSocketConnected: function () {
        this.$statusField.removeClass('connecting')
                         .text(r._('updating in real time...'))
    },

    _onWebSocketDisconnected: function () {
        this.$statusField.removeClass('connecting')
                         .addClass('error')
                         .text(r._('could not connect to update servers. please refresh.'))
    },

    _onWebSocketReconnecting: function (delay) {
        this.$statusField.removeClass('connecting')

        this._reconnectCountdown = new r.liveupdate.Countdown(_.bind(function (secondsRemaining) {
            var text = r.P_('lost connection to update server. retrying in %(delay)s second...',
                            'lost connection to update server. retrying in %(delay)s seconds...',
                            secondsRemaining).format({'delay': secondsRemaining})
            this.$statusField.text(text)
        }, this), delay)
    },

    _onRefresh: function () {
        // delay a random amount to reduce thundering herd
        var delay = Math.random() * 300 * 1000
        setTimeout(function () { location.reload() }, delay)
    },

    _onNewUpdate: function (data) {
        var $initial = this.$listing.find('tr.initial')

        // this must've been the first update. refresh to get a proper listing.
        if (!this.$listing.length)
            window.location.reload()

        var now = Date.now()
        _.each(data, function (thing) {
            var $newThing = $($.unsafe(thing.data.content))
            if (r.liveupdate.editor) {
                r.liveupdate.editor._addButtons($newThing.find('td'))
            }
            $initial.after($newThing)
            r.timetext.refreshOne($newThing.find('time.live'), now)
        })

        if (!this._pageVisible) {
            this._unreadUpdates += data.length
            Tinycon.setBubble(this._unreadUpdates)
        }
    },

    _onDelete: function (id) {
        $.things(id).remove()
    },

    _onStrike: function (id) {
        $.things(id).addClass('stricken')
    },

    _onActivityUpdated: function (visitors) {
        var text = visitors.count
        if (visitors.fuzzed)
            text = '~' + text

        // TODO: animate this?
        $('#visitor-count .count').text(text)
    },

    _onSettingsChanged: function (changes) {
        if ('title' in changes) {
            $('#liveupdate-title').text(changes['title'])
            $('#header .pagename a').text(changes['title'])
            document.title = r._('[live]') + ' ' + changes['title']
        }

        if ('description' in changes) {
            $('.sidebar .md').html($.unsafe(changes['description']))
        }
    },

    _loadMoreIfNearBottom: function () {
        var hasUpdates = (this.$listing.length != 0)
        var isLoading = this.$listing.hasClass('loading')
        var canLoadMore = (this.$table.find('.final').length == 0)

        if (!hasUpdates || isLoading || !canLoadMore)
            return

        // technically, window.innerHeight includes the horizontal
        // scrollbar if present. oh well.
        var bottomOfTable = this.$table.offset().top + this.$table.height()
        var topOfLastScreenful = bottomOfTable - window.innerHeight
        var nearBottom = ($(window).scrollTop() + 250 >= topOfLastScreenful)

        if (nearBottom)
            this._loadMore()
    },

    _loadMore: function () {
        var lastId = this.$table.find('tr:last-child').data('fullname')

        // in case we get stuck in a loop somehow, bail out.
        if (lastId == this.lastFetchedId)
            return

        var params = $.param({
                'bare': 'y',
                'after': lastId,
                'count': this.$table.find('tr.thing').length
            })
        var url = '/live/' + r.config.liveupdate_event + '/?' + params

        this.$listing.addClass('loading')

        $.ajax({
            'url': url,
            'dataType': 'html'
        })
            .done($.proxy(function (response) {
                var $fragment = $(response),
                    $newRows = $fragment.find('.liveupdate-listing tbody').children()

                this.$listing.trigger('more-updates', [$newRows])
                this.$table.append($newRows)
                this.lastFetchedId = lastId

                r.timetext.refresh()
            }, this))
            .always($.proxy(function () {
                this.$listing.removeClass('loading')
            }, this))
    },

    _fetchPixel: function () {
        if (!this._pageVisible) {
            this._needToFetchPixel = true
            return
        }

        var pixel = new Image()
        pixel.src = '//' + r.config.liveupdate_pixel_domain +
                    '/live/' + r.config.liveupdate_event + '/pixel.png' +
                    '?rand=' + Math.random()

        var delay = Math.floor(this._pixelInterval -
                               this._pixelInterval * Math.random() / 2)
        setTimeout($.proxy(this, '_fetchPixel'), delay)
    }
}

r.liveupdate.Countdown = function (tickCallback, delay) {
    this._tickCallback = tickCallback
    this._deadline = Date.now() + delay
    this._interval = setInterval(_.bind(this._onTick, this), 1000)

    this._onTick()
}
_.extend(r.liveupdate.Countdown.prototype, {
    cancel: function () {
        if (this._interval) {
            clearInterval(this._interval)
            this._interval = null
        }
    },

    _onTick: function () {
        var delayRemaining = this._deadline - Date.now()
            delayInSeconds = Math.round(delayRemaining / 1000)

        if (delayInSeconds >= 1) {
            this._tickCallback(delayInSeconds)
        } else {
            this.cancel()
        }
    }
})

r.liveupdate.init()
