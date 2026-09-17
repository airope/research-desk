from django.db import migrations

SQL = """
CREATE FUNCTION catalogues_protect_frozen_data() RETURNS trigger AS $$
BEGIN
 IF TG_TABLE_NAME = 'catalogues_auditevent' THEN
  RAISE EXCEPTION 'Catalogue audit events are immutable';
 ELSIF TG_TABLE_NAME = 'catalogues_entry' THEN
  IF NEW.raw IS DISTINCT FROM OLD.raw OR NEW.normalized IS DISTINCT FROM OLD.normalized
    OR NEW.catalogue_id IS DISTINCT FROM OLD.catalogue_id
    OR NEW.selection_id IS DISTINCT FROM OLD.selection_id
    OR NEW.provider IS DISTINCT FROM OLD.provider OR NEW.external_id IS DISTINCT FROM OLD.external_id
    OR NEW.local_id IS DISTINCT FROM OLD.local_id OR NEW.origin IS DISTINCT FROM OLD.origin THEN
   RAISE EXCEPTION 'Catalogue source snapshots are immutable';
  END IF;
 ELSIF TG_TABLE_NAME = 'catalogues_selection' THEN
  IF NEW.rows IS DISTINCT FROM OLD.rows OR NEW.errors IS DISTINCT FROM OLD.errors
    OR NEW.provenance IS DISTINCT FROM OLD.provenance OR NEW.kind IS DISTINCT FROM OLD.kind
    OR NEW.catalogue_id IS DISTINCT FROM OLD.catalogue_id THEN
   RAISE EXCEPTION 'Catalogue previews are immutable';
  END IF;
 END IF;
 RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER frozen_catalogue_audit BEFORE UPDATE OR DELETE ON catalogues_auditevent FOR EACH ROW EXECUTE FUNCTION catalogues_protect_frozen_data();
CREATE TRIGGER frozen_catalogue_entry BEFORE UPDATE ON catalogues_entry FOR EACH ROW EXECUTE FUNCTION catalogues_protect_frozen_data();
CREATE TRIGGER frozen_catalogue_selection BEFORE UPDATE ON catalogues_selection FOR EACH ROW EXECUTE FUNCTION catalogues_protect_frozen_data();
"""
REVERSE = """
DROP TRIGGER frozen_catalogue_audit ON catalogues_auditevent;
DROP TRIGGER frozen_catalogue_entry ON catalogues_entry;
DROP TRIGGER frozen_catalogue_selection ON catalogues_selection;
DROP FUNCTION catalogues_protect_frozen_data();
"""


class Migration(migrations.Migration):
    dependencies = [("catalogues", "0001_initial")]
    operations = [migrations.RunSQL(SQL, REVERSE)]
