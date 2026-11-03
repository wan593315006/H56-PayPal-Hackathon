# K1 controlled candidate review input

This is a controlled semantic projection of `K1_REQUIREMENT.md`, not a second
K1 requirement and not a Runtime input.  It makes the review vocabulary
explicit so the legacy compiler output can be judged by a structural quality
gate.  The original K1 requirement remains the normative candidate contract.

KernelReviewer submit CanonicalFact into FactHistory.
KernelReviewer verify FactHistory before derive DerivedState.
FactHistory 必须 derive the same DerivedState for the same history and version tuple.
CanonicalFact 必须 not project into DerivedState when it is invalidated.
CandidateTransition 必须 not mutate DerivedState during candidate review.
DecisionTrace 必须 record a rejected CandidateTransition without state mutation.
CandidateReviewRequested -> CandidateReviewValidated -> CandidateReviewArchived.
