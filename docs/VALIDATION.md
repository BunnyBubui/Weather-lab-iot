# Validation results

- Final-Project: five HTTP/security regression tests passed; MySQL-backed signup, login, profile ownership, listing ownership, forged-username rejection and logout smoke checks passed. Expo web export passed after aligning React/React DOM with the React Native peer dependency.
- Sports Results and Ticketing portfolio snapshots: frontend production builds passed. Original media was excluded; source uses neutral placeholders. Ticketing snapshot no longer runs obsolete react-snap automatically.
- electricity-logger and 67100784-web: frontend production builds passed.
- prg-01-67100784: Maven package build passed using a full JDK; tests requiring a configured application database were not run.
- Weather-lab-iot: MQTT/MongoDB/FastAPI smoke checks passed for malformed JSON handling, partial-reading merge, latest/history APIs and online status.
- Changed JavaScript/JSX/TypeScript and Python source passed syntax parsing. Gitleaks found no matches in the checked-out project source after cleanup, with installed dependencies and build caches excluded.

These results are scoped to the commands above. Android device behavior, full production deployments, model accuracy, all historical Git objects and third-party dataset/media rights were not certified. Bundle-size warnings remain in some frontend builds.
