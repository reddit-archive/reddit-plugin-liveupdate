!function(r, Backbone, $, _) {
  'use strict'

  var exports = r.liveupdate.report = {}

  exports.ReportForm = Backbone.View.extend({
    el: '#report',

    events: {
      'click .report-button': 'onOpen',
      'click .cancel': 'onCancel',
      'confirm .admin': 'onAdminAction',
      'change .report-type': 'onReportTypeSelected',
      'submit': 'onSubmit',
    },

    initialize: function() {
      this.$button = this.$el.children('.report-button')
      this.$form = this.$el.children('form')
      this.$adminButton = this.$el.find('button.admin')

      new r.ui.ConfirmButton({el: this.$adminButton})
    },

    _setFormVisibility: function(formVisible) {
      this.$button.toggle(!formVisible)
      this.$form.toggle(formVisible)
    },

    onOpen: function() {
      this._setFormVisibility(true)
    },

    onCancel: function(ev) {
      this._setFormVisibility(false)
      ev.preventDefault()
    },

    onReportTypeSelected: function() {
      this.$('[type=submit]').prop('disabled', false)
    },

    onSubmit: function(ev) {
      var _this = this
      var $radio = this.$el.find('input[type=radio]:checked')
      var reportType = $radio.val()
      var reportDescription = $radio.parent().text()

      this.$el.text(r._('submitting report…'))

      r.ajax({
        type: 'POST',
        dataType: 'json',
        url: '/api/live/' + r.config.liveupdate_event + '/report',
        data: {
          'type': reportType,
        },
      }).then(function() {
        _this.$el.html(r.templates.make('liveupdate/reported', {
          text: r._('you reported this live thread for: %(violation)s').format({
            violation: reportDescription,
          }),
        }))
      })

      ev.preventDefault()
    },

    onAdminAction: function() {
      post_admin_api(this.$adminButton, r.config.liveupdate_event).then(function() {
        window.location.reload();
      });
    },
  });

  var post_admin_api = function($btn, thing_id) {
      var action = $btn.data('action')

      var url = '/api/live/' + thing_id + '/' + action

      return r.ajax({
        type: 'POST',
        url: url,
      });
  };

  $('#siteTable .liveupdate-event button.admin').each(function() {
    new r.ui.ConfirmButton({el: $(this)});
  });
  $('#siteTable .liveupdate-event .admin').on("confirm", function() {
    var $this = $(this);
    var $btn = $(this).children("button")
    post_admin_api($btn, $btn.data("threadid")).success(function() {
      $this.text("success");
    }).error(function() {
      $this.text("fail");
    });
  });
}(r, Backbone, jQuery, _)
