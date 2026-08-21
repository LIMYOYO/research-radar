"""Named venue presets kept as explicit configuration, never ranking truth."""

from __future__ import annotations


INFORMS_JOURNALS = (
    "Decision Analysis",
    "Information Systems Research",
    "INFORMS Journal on Applied Analytics",
    "INFORMS Journal on Computing",
    "INFORMS Journal on Data Science",
    "INFORMS Journal on Optimization",
    "INFORMS Transactions on Education",
    "Management Science",
    "Manufacturing & Service Operations Management",
    "Marketing Science",
    "Mathematics of Operations Research",
    "Operations Research",
    "Organization Science",
    "Service Science",
    "Stochastic Systems",
    "Strategy Science",
    "Transportation Science",
)

INFORMS_CORE = (
    "Management Science",
    "Operations Research",
    "Manufacturing & Service Operations Management",
    "Information Systems Research",
    "Marketing Science",
    "Organization Science",
    "INFORMS Journal on Computing",
    "Transportation Science",
)

UTD24_JOURNALS = (
    "The Accounting Review",
    "Journal of Accounting and Economics",
    "Journal of Accounting Research",
    "Journal of Finance",
    "Journal of Financial Economics",
    "The Review of Financial Studies",
    "Information Systems Research",
    "INFORMS Journal on Computing",
    "MIS Quarterly",
    "Journal of Consumer Research",
    "Journal of Marketing",
    "Journal of Marketing Research",
    "Marketing Science",
    "Management Science",
    "Operations Research",
    "Journal of Operations Management",
    "Manufacturing & Service Operations Management",
    "Production and Operations Management",
    "Academy of Management Journal",
    "Academy of Management Review",
    "Administrative Science Quarterly",
    "Organization Science",
    "Journal of International Business Studies",
    "Strategic Management Journal",
)

VENUE_PRESETS = {
    "informs": INFORMS_JOURNALS,
    "informs-core": INFORMS_CORE,
    "utd24": UTD24_JOURNALS,
}
