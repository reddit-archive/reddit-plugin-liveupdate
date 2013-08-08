r.liveupdate = {
    init: function () {
        this.$listing = $('.liveupdate-listing')
        this.$table = this.$listing.find('table tbody')
        this.$showmore = $('.showmore')
        this.$loading = $('<div class="showmore">' + r._('loading&hellip;') + '</div>')

        $('body').on('click', '.showmore', $.proxy(this, 'onShowMore'))
    },

    onShowMore: function () {
        var lastId = this.$table.find('tr:last-child').data('fullname'),
            params = $.param({
                'after': lastId,
                'count': this.$table.find('tr.thing').length
            }),
            url = '/live/' + r.config.liveupdate_event + '/?' + params

        this.$showmore.replaceWith(this.$loading)

        $.ajax({
            'url': url,
            'dataType': 'html',
            'success': $.proxy(function (response) {
                var fragment = $(response),
                    newRows = fragment.find('.liveupdate-listing tbody').children()

                if (newRows.filter('.final').length == 0) {
                    this.$loading.replaceWith(this.$showmore)
                } else {
                    this.$loading.remove()
                }

                this.$listing.trigger('more-updates', [newRows])
                this.$table.append(newRows)

                r.timetext.refresh()
            }, this),
            'error': function () {
                // TODO
                console.log('sad panda')
            }
        })
    }
}

r.liveupdate.init()
