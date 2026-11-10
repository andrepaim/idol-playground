# Reviewed canine walking in the app

Issue #31 continues parent #26. Implement a separate, recoverable walking job for the reviewed 34-joint canine topology. Preserve source rigs, geometry, colors and existing generation. Reject unsupported topology; require explicit paw-role review. This is a bounded experimental profile, not arbitrary-species rigging or a game-ready certification.

The motion pass replaces the pace-like trial with a four-beat lateral sequence (hind-left, fore-left, hind-right, fore-right), conservative body motion, surface-feedback paw placement and continuous looping. The preset is procedural and informed by the previous recorded-motion trial; it does not redistribute that capture or claim full motion retargeting. See the [University of Minnesota veterinary gait reference](https://vanat.ahc.umn.edu/gaits/walk.html).

## Implementation and acceptance

1. Test periodic trajectories, four distinct footfalls, support and explicit profile validation. Implement reusable CPU motion/profile helpers and a native Blender worker using the existing UniRig environment. Transfer skin continuously from the retained source FBX, without changing source files.
2. Produce separate in-place and forward GLBs, an FBX and editable Blend file. Check evaluated surface contact, motion, loop endpoints and forward displacement; reimport native exports. Compare the actual owner's dog against the accepted trial locally. Report measured limitations rather than promising naturalness from a structural check.
3. Add exclusive cancellable animation jobs, progress/ETA, safe persisted reopening and setup/source validation. Release cached Idol before native workers. Expose only safe file URLs and retain source linkage.
4. Add explicit paw review and speed/travel choices after a supported rig; animated preview, play/pause, scrub, speed, floor and skeleton controls; downloadable variants and reopened saved walks. Preserve existing rig diagnostic and splat/mesh controls.
5. Validate unit/API/lifecycle tests, native export checks, browser acceptance and real RTX 3060 cached Idol → walking/cancel/retry → Idol reload. Use isolated outputs and a separate app port; never interrupt active owner generation. Review the combined diff, merge a PR and check CI on the combined main commit. Install the result into the idle local main app.

Risk: native workers can be slow and generated anatomy remains approximate. Cancellation must reap children before releasing the exclusive slot. Saved jobs are additive; original jobs and model caches must remain untouched. Existing source artifacts are private and must never enter commits or public evidence. No new model download, paid service, release or owner-media publication is required.

Generic anatomical mapping, other species and actual game-engine acceptance remain in parent #26 and the existing engine issue. This increment is complete only when the bounded supported profile is usable through the app with measured export/contact evidence and the required checks above.
