r.liveupdate = {
    init: function () {
        this.$listing = $('.liveupdate-listing')
        this.$table = this.$listing.find('table tbody')

        this.$listing.find('nav.nextprev').remove()
        $(window)
            .scroll($.proxy(this, '_loadMoreIfNearBottom'))
            .scroll()  // in case of a short page / tall window

        r.liveupdate.SocketListener.init(r.config.liveupdate_websocket)
    },

    _loadMoreIfNearBottom: function () {
        var isLoading = this.$listing.hasClass('loading')
        var canLoadMore = (this.$table.find('.final').length == 0)

        if (isLoading || !canLoadMore)
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
    }
}

r.liveupdate.SocketListener = {
    _backoffTime: 2000,
    _maximumRetries: 8,

    init: function (url) {
        var websocketsAvailable = 'WebSocket' in window
        if (websocketsAvailable && url) {
            this.$listing = $('.liveupdate-listing')
            this.$statusField = this.$listing.find('tr.initial td')

            this._socketUrl = url
            this._connectionAttempts = 0
            this._connect()
        }
    },

    _connect: function () {
        if (this._connectionAttempts > this._maximumRetries) {
            this.$statusField.addClass('error')
                             .text(r._('could not connect to update servers. please refresh.'))
            return
        }

        r.debug('liveupdate websocket: connecting...')

        this.$statusField.addClass('connecting')

        this._socket = new WebSocket(this._socketUrl)
        this._socket.onopen = $.proxy(this, '_onSocketOpen')
        this._socket.onmessage = $.proxy(this, '_onMessage')
        this._socket.onclose = $.proxy(this, '_onSocketClose')
        this._connectionAttempts += 1
    },

    _onSocketOpen: function () {
        r.debug('liveupdate websocket: connected')
        this.$statusField.removeClass('connecting')
        this.$statusField.text(r._('updating in real time...'))
    },

    _onSocketClose: function (ev) {
        r.debug('liveupdate websocket: lost connection')
        this.$statusField.removeClass('connecting')

        var delay = this._backoffTime * Math.pow(2, this._connectionAttempts)
        setTimeout($.proxy(this, '_connect'), delay)
    },

    _onMessage: function (ev) {
        var parsed = JSON.parse(ev.data)
        var $initial = this.$listing.find('tr.initial')

        // this must've been the first update. refresh to get a proper listing.
        if (!this.$listing.length)
            window.location.reload()

        _.each(parsed, function (thing) {
            var $newThing = $($.unsafe(thing.data.content))
            if (r.liveupdate.editor) {
                r.liveupdate.editor._addButtons($newThing.find('td'))
            }
            $initial.after($newThing)
        })
    }
}

r.liveupdate.init()
