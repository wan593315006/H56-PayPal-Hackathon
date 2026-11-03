# K0 controlled candidate review input

This is a controlled semantic projection of `K0_REQUIREMENT.md`, not a second
K0 requirement and not a Runtime input.  It makes the review vocabulary
explicit so the legacy compiler output can be judged by a structural quality
gate.  The original K0 requirement remains the normative candidate contract.

KernelReviewer submit CanonicalFact into FactHistory.
KernelReviewer verify CanonicalFact before record FactHistory.
CanonicalFact 必须 preserve source, subject, evidence, and version before record FactHistory.
FactHistory 必须 append CanonicalFact without overwrite.
CandidateTransition 必须 not mutate DerivedState when a candidate is denied.
DecisionTrace 必须 record the denial decision for CandidateTransition.
CandidateReviewRequested -> CandidateReviewValidated -> CandidateReviewArchived.
