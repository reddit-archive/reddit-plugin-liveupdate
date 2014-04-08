from pylons.i18n import N_

from r2.lib.permissions import PermissionSet


class ReporterPermissionSet(PermissionSet):
    info = {
        "update": {
            "title": N_("update"),
            "description": N_("post updates"),
        },

        "manage": {
            "title": N_("manage reporters"),
            "description": N_("add, remove, and change permissions of reporters"),
        },

        "settings": {
            "title": N_("settings"),
            "description": N_("change the title, description, and timezone"),
        },

        "edit": {
            "title": N_("edit"),
            "description": N_("strike and delete others' updates"),
        },
    }

    def allow(self, permission):
        if self.is_superuser():
            return True
        return self.get(permission, False)

    def without(self, permission):
        if self.is_superuser():
            permissions = {k: True for k in self.info}
        else:
            permissions = self.copy()

        permissions.pop(permission, None)
        return ReporterPermissionSet(permissions)


ReporterPermissionSet.SUPERUSER = ReporterPermissionSet.loads("+all")
ReporterPermissionSet.NONE = ReporterPermissionSet.loads("")
