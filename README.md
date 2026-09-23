# Sri NRI Junior College Management System

## Environment Variables for Production Media Storage (Render Deployment)

To enable durable cloud media storage on Render (so uploaded student photos survive redeployments and restarts), configure the following environment variables in the Render Dashboard under **Environment**:

| Variable Name | Required? | Example Value | Description |
|---|---|---|---|
| `AWS_ACCESS_KEY_ID` | **Yes** | `AKIAIOSFODNN7EXAMPLE` | AWS IAM Access Key ID with S3 read/write permissions |
| `AWS_SECRET_ACCESS_KEY` | **Yes** | `wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY` | AWS IAM Secret Access Key |
| `AWS_STORAGE_BUCKET_NAME` | **Yes** | `sri-nri-college-media` | Name of your S3 Bucket |
| `AWS_S3_REGION_NAME` | Optional | `ap-south-1` | AWS S3 Region Name (Default: `ap-south-1`) |
| `AWS_LOCATION` | Optional | `media` | Subfolder inside S3 bucket (Default: `media`) |
| `AWS_S3_CUSTOM_DOMAIN` | Optional | `media.srinri.in` | CloudFront / Custom Domain URL if applicable |

### Behavior:
- When `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and `AWS_STORAGE_BUCKET_NAME` are set in Render, Django automatically routes all file uploads (student photos, lab reports, etc.) to AWS S3 using `django-storages`.
- When these credentials are not set (such as in local development), Django automatically falls back to local disk file storage (`FileSystemStorage`), and WhiteNoise / Django URL routing serves media seamlessly.
