from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.execute("""
    CREATE TABLE IF NOT EXISTS tasks (
      id UUID PRIMARY KEY,
      type TEXT NOT NULL,
      language TEXT,
      created_at TIMESTAMPTZ DEFAULT now(),
      status TEXT NOT NULL,
      latency_ms INT,
      model_used TEXT,
      template_ver TEXT
    );
    """)
    op.execute("""
    CREATE TABLE IF NOT EXISTS rewards (
      id UUID PRIMARY KEY,
      task_id UUID REFERENCES tasks(id) ON DELETE CASCADE,
      model TEXT NOT NULL,
      success BOOLEAN NOT NULL,
      latency_ms INT,
      human_score INT,
      created_at TIMESTAMPTZ DEFAULT now()
    );
    """)
    op.execute("""
    CREATE TABLE IF NOT EXISTS bandit_stats (
      model TEXT NOT NULL,
      feature_hash TEXT NOT NULL,
      runs INT DEFAULT 0,
      reward_sum DOUBLE PRECISION DEFAULT 0,
      reward_sq_sum DOUBLE PRECISION DEFAULT 0,
      last_updated TIMESTAMPTZ DEFAULT now(),
      PRIMARY KEY (model, feature_hash)
    );
    """)

def downgrade():
    op.execute("DROP TABLE IF EXISTS bandit_stats;")
    op.execute("DROP TABLE IF EXISTS rewards;")
    op.execute("DROP TABLE IF EXISTS tasks;")
