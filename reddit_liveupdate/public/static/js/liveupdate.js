r.liveupdate = {
    _pixelInterval: 10 * 60 * 1000,
    _favicon: 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAMAAAAoLQ9TAAAA/1BMVEUpLzY+PDpGSk5HR0dKTlNSW2VTXGVVXmdWWl5bYWZdZGtfanVfbHpgXVtianNjbXhkZWdkam1lcX1nc4BpdYJqa2xscHZucHJueYRvfoxwfIhxcG93e4B3h5h4iJh5ipt7gIB8ipl+fn6BgYGImKOJh4aKjY2Mna6NobSOn7CQo7iar8Wfnp2juM6lo6Gmuc6mu8moqaqsw9etwcmurq6vrauxyN2xyN+0s7K+u7m/1u7C2vPF3fbI4PrJ4fvJ4/7Ly8vPzMnP6P7S0tLT0c/W8P/Z19Xd9/7d+P7e3Nrw8PDz9vT69/T+EA/+MjD+pqT+srD+w8H+zsz+/v7///9fla50AAAAuElEQVR42l2P2RaBUBhGT0WZ54jIPM8h0zE7SBL97/8uYoXFvtwXe30fIn8ggn94i8XMGSkFQvmPwFXvwOe/OGyx3OJYF+OUq26LcS2LMs05Xj0bPY+QDFc6k1bOnRQ8PYLiKlXW4IlWptQ4QWlxCIZ+h7tuwFBME9RgAG5XE8zrDYBpWNEEfElY0RO7Aejvzrs+wIa1xFGmp7AuFoprmNLya4fC8aP9YT/iOeX9pS1Fg1GpbZ/74wFo2jf64C4agwAAAABJRU5ErkJggg==',

    init: function () {
        this.$listing = $('.liveupdate-listing')
        this.$table = this.$listing.find('table tbody')
        this.$statusField = this.$listing.find('tr.initial td')
        this._embedViewer = new r.liveupdate.EmbedViewer()

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
                'message:embeds_ready': this._onEmbedsReady,
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

        this._pixelsFetched = 0
        this._fetchPixel()
        this._embedViewer.init()
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

    _onNewUpdate: function (thing) {
        var $initial = this.$listing.find('tr.initial')

        // this must've been the first update. refresh to get a proper listing.
        if (!this.$listing.length)
            window.location.reload()

        var $newThing = $($.unsafe(thing.rendered))
        this.$listing.trigger('more-updates', [$newThing])
        $initial.after($newThing)
        r.timetext.refreshOne($newThing.find('time.live'))

        if (!this._pageVisible) {
            this._unreadUpdates += 1
            Tinycon.setBubble(this._unreadUpdates)
        }
    },

    _onEmbedsReady: function (data) {
        $('tr.id-LiveUpdate_' + data.liveupdate_id)
            .data('embeds', data.media_embeds)
            .addClass('pending-embed')

        $(window).trigger('liveupdate:refreshEmbeds')
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

        // we don't need to fire a heartbeat for GA on the first pixel request, also
        // google analytics might not be enabled, so only use this if we're sure it's safe
        if (this._pixelsFetched > 0 && window._gaq) {
            // TODO: do something when we hit the 500 ping limit
            _gaq.push(['_trackEvent', 'Heartbeat', 'Heartbeat', '', 0, true]);
        }

        this._pixelsFetched += 1

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

/**
 * EmbedViewer displays matching embeddable links inline nicely for live updates (like tweets).
 * Workflow:
 * 1. On scroll, see if updates with pending embeds are in the viewport (denoted by .pending-embed)
 * 2. For each of those updates, load all of the embeds within the update and replace them with their iframes.
**/
r.liveupdate.EmbedViewer = r.ScrollUpdater.extend({
    selector: '.pending-embed',
    _embedBase: '//' + r.config.media_domain + '/mediaembed/liveupdate/' + r.config.liveupdate_event,

    _listen: function() {
        $(window).on('liveupdate:refreshEmbeds', $.proxy(this, 'restart'))
        $(window).on('message', this._handleMessage)
        r.ScrollUpdater.prototype._listen.apply(this, arguments);
    },

    update: function($el) {
        var updateId = $el.data('fullname'),
            embeds = $el.data('embeds')

        if (!$el.hasClass('pending-embed')) {
            return
        }
        $el.removeClass('pending-embed')

        _.each(embeds, function(embed, embedIndex) {
            var $link = $el.find('a[href="' + embed.url + '"]'),
                embedUri = this._embedBase + '/' + updateId + '/' + embedIndex,
                iframe = $('<iframe />').attr({
                    'class': 'embedFrame embed-' + embedIndex,
                    'src': embedUri,
                    'width': embed.width,
                    'height': embed.height || 200,
                    'scrolling': 'no',
                    'frameborder': 0
                })
            r.debug("Rendering embed for link: ", $link)
            $link.replaceWith(iframe)
        }, this)
    },

    _handleMessage: function(e) {
       var ev = e.originalEvent

       if (ev.origin.replace(/^https?:\/\//,'') !== r.config.media_domain) {
           return false
       }

       var data = JSON.parse(ev.data)
       if (data.action === 'dimensionsChange') {
           /* Yuck. A good reason to give embeds unique IDs. */
           var $embedFrame = $('.id-LiveUpdate_' + data.updateId + ' .embed-' + data.embedIndex)

           $embedFrame.attr({
               'width': Math.min(data.width, 480),
               'height': data.height
           })
       }
    },

    init: function() {
        this.start()
    }
})


r.liveupdate.init()
