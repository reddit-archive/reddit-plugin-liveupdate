r.liveupdate = {
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
                'message:update': this._onNewUpdate
            }, this)
        }
    },

    _onWebSocketConnecting: function () {
        this.$statusField.addClass('connecting')
                         .text(r._('connecting to update server...'))
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
                         .text(r._('lost connection to update server. one moment...'))
    },

    _onNewUpdate: function (data) {
        var $initial = this.$listing.find('tr.initial')

        // this must've been the first update. refresh to get a proper listing.
        if (!this.$listing.length)
            window.location.reload()

        _.each(data, function (thing) {
            var $newThing = $($.unsafe(thing.data.content))
            if (r.liveupdate.editor) {
                r.liveupdate.editor._addButtons($newThing.find('td'))
            }
            $initial.after($newThing)
        })
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
    }
}

r.liveupdate.init()
