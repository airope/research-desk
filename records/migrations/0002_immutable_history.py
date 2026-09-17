from django.db import migrations

SQL = """
CREATE FUNCTION records_reject_history_mutation() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'Immutable history rows cannot be updated or deleted';
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER immutable_source_version BEFORE UPDATE OR DELETE ON records_sourcerecordversion
FOR EACH ROW EXECUTE FUNCTION records_reject_history_mutation();
CREATE TRIGGER immutable_review_decision BEFORE UPDATE OR DELETE ON records_reviewdecision
FOR EACH ROW EXECUTE FUNCTION records_reject_history_mutation();
CREATE TRIGGER immutable_match_proposal BEFORE UPDATE OR DELETE ON records_matchproposal
FOR EACH ROW EXECUTE FUNCTION records_reject_history_mutation();
"""
REVERSE = """
DROP TRIGGER immutable_source_version ON records_sourcerecordversion;
DROP TRIGGER immutable_review_decision ON records_reviewdecision;
DROP TRIGGER immutable_match_proposal ON records_matchproposal;
DROP FUNCTION records_reject_history_mutation();
"""


class Migration(migrations.Migration):
    dependencies = [("records", "0001_initial")]
    operations = [migrations.RunSQL(SQL, REVERSE)]
