# IncuBrix Script-to-B-roll Video Engine — Sources and Licensing

## 1. Purpose

This file records the external footage source used by the prototype, the sample clip IDs downloaded during testing, and the checks required before redistribution or public demonstration.

## 2. Footage Provider

- Provider: Pixabay
- Content type: Stock video footage
- Retrieval method: Pixabay video API through the project's footage downloader
- Search method: Text query and metadata/tag keyword matching
- API credentials: Stored locally in `.env`; do not commit credentials to version control.
- API documentation: https://pixabay.com/api/docs/
- Provider terms: https://pixabay.com/service/terms/

## 3. Sample Clips Used During Testing

The following video IDs were downloaded and used in local prototype tests.

| Pixabay video ID | Local filename | Test context | Licence review |
|---|---|---|---|
| 243201 | `pixabay_243201.mp4` | Village-related script | Required |
| 130226 | `pixabay_130226.mp4` | Farm and harvest script | Required |
| 288051 | `pixabay_288051.mp4` | Market-related script | Required |

Expected local directory: `test_inputs/broll/`

The IDs and filenames above document retrieval during development. They do not, by themselves, prove that the footage is appropriate for every scene or cleared for every intended use.

## 4. Required Checks Before Public Release

For each clip used in a submitted or publicly shared video:

1. Open the original provider page for the specific video ID.
2. Confirm the applicable licence and terms on the date of use.
3. Check whether attribution is required and preserve any required attribution.
4. Review restrictions on redistribution, modification, and commercial use.
5. Watch the actual downloaded footage and confirm that it matches the intended scene.
6. Check for visible people, trademarks, sensitive content, and other material that may require additional review.
7. Record the original provider URL, retrieval date, licence findings, and any attribution in the final source manifest.
8. Replace a clip if its licence or relevance cannot be established.

## 5. Current Implementation and Limitations

- The downloader searches Pixabay and retrieves candidate footage.
- Scene matching uses metadata and keyword overlap.
- The prototype records source metadata and marks licensing as requiring review.
- Metadata matching is not proof of visual relevance.
- A successful download does not establish licence clearance.
- A generated video should not be described as fully licence-cleared until the individual source records have been checked.

## 6. Source Manifest Recommendations

For every selected clip, retain the following fields where available:

- Provider name
- Provider video ID
- Original provider page URL
- Download date and time
- Original search query
- Provider metadata and tags
- Local filename
- Licence URL and review result
- Attribution text, if required
- Human visual-relevance review status

## 7. Responsible Use Statement

This document is a development record, not a legal opinion or a guarantee of licensing rights. Verify the current provider terms and the individual clip information before external distribution.