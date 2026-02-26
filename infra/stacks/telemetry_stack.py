"""Complete AWS infrastructure stack for CAN Telemetry Platform."""

from pathlib import Path

from aws_cdk import (
    Duration,
    RemovalPolicy,
    Stack,
    CfnOutput,
    aws_s3 as s3,
    aws_lambda as lambda_,
    aws_apigatewayv2 as apigwv2,
    aws_apigatewayv2_integrations as apigwv2_integrations,
    aws_glue as glue,
    aws_athena as athena,
    aws_cognito as cognito,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    aws_iam as iam,
    aws_s3_notifications as s3n,
)
from constructs import Construct


class TelemetryStack(Stack):
    """Complete infrastructure stack for CAN Telemetry Platform."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # =======================
        # S3 BUCKETS
        # =======================

        # Data lake bucket
        self.data_bucket = s3.Bucket(
            self,
            "DataLakeBucket",
            bucket_name=f"telemetry-data-lake-{self.account}",
            versioned=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="ArchiveRawData",
                    prefix="raw/",
                    transitions=[
                        s3.Transition(
                            storage_class=s3.StorageClass.GLACIER,
                            transition_after=Duration.days(90),
                        )
                    ],
                )
            ],
            cors=[
                s3.CorsRule(
                    allowed_methods=[
                        s3.HttpMethods.GET,
                        s3.HttpMethods.HEAD,
                    ],
                    allowed_origins=["*"],  # Restrict in production
                    allowed_headers=["*"],
                    max_age=3000,
                )
            ],
            removal_policy=RemovalPolicy.RETAIN,
        )

        # Athena results bucket
        self.athena_results_bucket = s3.Bucket(
            self,
            "AthenaResultsBucket",
            bucket_name=f"telemetry-athena-results-{self.account}",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="DeleteOldResults",
                    expiration=Duration.days(30),
                )
            ],
            removal_policy=RemovalPolicy.DESTROY,
        )

        # Frontend bucket
        self.frontend_bucket = s3.Bucket(
            self,
            "FrontendBucket",
            bucket_name=f"telemetry-frontend-{self.account}",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # =======================
        # GLUE DATABASE & CRAWLER
        # =======================

        # Glue database
        self.glue_database = glue.CfnDatabase(
            self,
            "TelemetryDatabase",
            catalog_id=self.account,
            database_input=glue.CfnDatabase.DatabaseInputProperty(
                name="telemetry_db",
                description="CAN telemetry data catalog",
            ),
        )

        # Glue crawler role
        crawler_role = iam.Role(
            self,
            "GlueCrawlerRole",
            assumed_by=iam.ServicePrincipal("glue.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSGlueServiceRole"
                )
            ],
        )

        self.data_bucket.grant_read(crawler_role)

        # Glue crawler for raw and decoded data
        glue.CfnCrawler(
            self,
            "TelemetryCrawler",
            name="telemetry-crawler",
            role=crawler_role.role_arn,
            database_name=self.glue_database.ref,
            targets=glue.CfnCrawler.TargetsProperty(
                s3_targets=[
                    glue.CfnCrawler.S3TargetProperty(
                        path=f"s3://{self.data_bucket.bucket_name}/raw/"
                    ),
                    glue.CfnCrawler.S3TargetProperty(
                        path=f"s3://{self.data_bucket.bucket_name}/decoded/"
                    ),
                ]
            ),
            schema_change_policy=glue.CfnCrawler.SchemaChangePolicyProperty(
                update_behavior="UPDATE_IN_DATABASE",
                delete_behavior="LOG",
            ),
        )

        # =======================
        # ATHENA WORKGROUP
        # =======================

        self.athena_workgroup = athena.CfnWorkGroup(
            self,
            "TelemetryWorkgroup",
            name="telemetry-workgroup",
            work_group_configuration=athena.CfnWorkGroup.WorkGroupConfigurationProperty(
                result_configuration=athena.CfnWorkGroup.ResultConfigurationProperty(
                    output_location=f"s3://{self.athena_results_bucket.bucket_name}/query-results/",
                    encryption_configuration=athena.CfnWorkGroup.EncryptionConfigurationProperty(
                        encryption_option="SSE_S3"
                    ),
                ),
                enforce_work_group_configuration=True,
                publish_cloud_watch_metrics_enabled=True,
            ),
        )

        # =======================
        # LAMBDA LAYER (cantools + pyarrow)
        # =======================

        # Create Lambda layer for decoder dependencies
        # Note: In production, build this layer separately with proper packaging
        self.decoder_layer = lambda_.LayerVersion(
            self,
            "DecoderLayer",
            code=lambda_.Code.from_asset(
                "../processing/decoder",
                exclude=[
                    "venv/*",
                    ".venv/*",
                    "__pycache__/*",
                    "*.pyc",
                    ".git/*",
                    "tests/*",
                ],
            ),
            compatible_runtimes=[lambda_.Runtime.PYTHON_3_12],
            description="cantools and pyarrow for CAN decoding",
        )

        # =======================
        # LAMBDA - DECODER
        # =======================

        # Decoder Lambda role
        decoder_role = iam.Role(
            self,
            "DecoderLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ],
        )

        self.data_bucket.grant_read_write(decoder_role)

        # Decoder Lambda function
        self.decoder_lambda = lambda_.Function(
            self,
            "DecoderFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="handler.handler",
            code=lambda_.Code.from_asset(
                "../processing/decoder",
                exclude=[
                    "venv/*",
                    ".venv/*",
                    "__pycache__/*",
                    "*.pyc",
                    ".git/*",
                    "tests/*",
                ],
            ),
            role=decoder_role,
            timeout=Duration.minutes(5),
            memory_size=1024,
            environment={
                "DBC_BUCKET": self.data_bucket.bucket_name,
                "DBC_KEY": "dbc/ev_powertrain.dbc",
                "DECODED_PREFIX": "decoded",
            },
            layers=[self.decoder_layer],
        )

        # S3 trigger for decoder
        self.data_bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,
            s3n.LambdaDestination(self.decoder_lambda),
            s3.NotificationKeyFilter(prefix="raw/", suffix=".parquet"),
        )

        # =======================
        # LAMBDA - API BACKEND
        # =======================

        # Create Lambda layer for API dependencies
        self.api_layer = lambda_.LayerVersion(
            self,
            "ApiDependenciesLayer",
            code=lambda_.Code.from_asset(
                "../backend/lambda-layer",
            ),
            compatible_runtimes=[lambda_.Runtime.PYTHON_3_12],
            description="FastAPI, Mangum, Boto3, and other API dependencies",
        )

        # API Lambda role
        api_role = iam.Role(
            self,
            "ApiLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ],
        )

        # Grant Athena permissions
        api_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "athena:StartQueryExecution",
                    "athena:GetQueryExecution",
                    "athena:GetQueryResults",
                    "athena:StopQueryExecution",
                ],
                resources=[
                    f"arn:aws:athena:{self.region}:{self.account}:workgroup/*"
                ],
            )
        )

        # Grant Glue permissions
        api_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "glue:GetDatabase",
                    "glue:GetTable",
                    "glue:GetPartitions",
                ],
                resources=[
                    f"arn:aws:glue:{self.region}:{self.account}:catalog",
                    f"arn:aws:glue:{self.region}:{self.account}:database/{self.glue_database.ref}",
                    f"arn:aws:glue:{self.region}:{self.account}:table/{self.glue_database.ref}/*",
                ],
            )
        )

        # Grant S3 permissions for Athena results and data
        self.athena_results_bucket.grant_read_write(api_role)
        self.data_bucket.grant_read(api_role)

        # API Lambda function (single function with Mangum)
        self.api_lambda = lambda_.Function(
            self,
            "ApiFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="lambda_handler.handler",
            code=lambda_.Code.from_asset(
                "../backend",
                exclude=[
                    "venv/*",
                    ".venv/*",
                    "__pycache__/*",
                    "*.pyc",
                    ".git/*",
                    "tests/*",
                    "*.md",
                    ".pytest_cache/*",
                    ".ruff_cache/*",
                    "lambda-layer/*",
                ],
            ),
            role=api_role,
            timeout=Duration.seconds(120),  # Increased for Athena queries
            memory_size=1024,  # Increased for faster execution
            environment={
                "ATHENA_DATABASE": self.glue_database.ref,
                "ATHENA_RESULTS_BUCKET": self.athena_results_bucket.bucket_name,
                "S3_DATA_BUCKET": self.data_bucket.bucket_name,
                # Note: AWS_REGION is automatically provided by Lambda runtime
            },
            layers=[self.api_layer],
        )

        # =======================
        # COGNITO (OPTIONAL)
        # =======================

        # User pool
        self.user_pool = cognito.UserPool(
            self,
            "TelemetryUserPool",
            user_pool_name="telemetry-users",
            self_sign_up_enabled=True,
            sign_in_aliases=cognito.SignInAliases(email=True, username=True),
            auto_verify=cognito.AutoVerifiedAttrs(email=True),
            password_policy=cognito.PasswordPolicy(
                min_length=8,
                require_lowercase=True,
                require_uppercase=True,
                require_digits=True,
                require_symbols=False,
            ),
            removal_policy=RemovalPolicy.DESTROY,
        )

        # App client
        self.user_pool_client = self.user_pool.add_client(
            "TelemetryAppClient",
            auth_flows=cognito.AuthFlow(user_password=True, user_srp=True),
            o_auth=cognito.OAuthSettings(
                flows=cognito.OAuthFlows(implicit_code_grant=True),
                scopes=[cognito.OAuthScope.OPENID, cognito.OAuthScope.EMAIL],
                callback_urls=["http://localhost:5173"],  # Add production URL
            ),
        )

        # =======================
        # API GATEWAY (HTTP API)
        # =======================

        # Lambda integration for HTTP API
        api_integration = apigwv2_integrations.HttpLambdaIntegration(
            "ApiIntegration",
            self.api_lambda,
        )

        # HTTP API (faster and cheaper than REST API)
        self.api = apigwv2.HttpApi(
            self,
            "TelemetryHttpApi",
            api_name="telemetry-http-api",
            description="CAN Telemetry Platform HTTP API",
            cors_preflight=apigwv2.CorsPreflightOptions(
                allow_origins=["*"],  # Restrict in production
                allow_methods=[
                    apigwv2.CorsHttpMethod.GET,
                    apigwv2.CorsHttpMethod.POST,
                    apigwv2.CorsHttpMethod.PUT,
                    apigwv2.CorsHttpMethod.DELETE,
                    apigwv2.CorsHttpMethod.OPTIONS,
                ],
                allow_headers=["Content-Type", "Authorization", "X-Requested-With"],
                max_age=Duration.hours(1),
            ),
            default_integration=api_integration,
        )

        # =======================
        # CLOUDFRONT + FRONTEND
        # =======================

        # Origin Access Identity for S3
        oai = cloudfront.OriginAccessIdentity(
            self,
            "FrontendOAI",
            comment="OAI for telemetry frontend",
        )

        self.frontend_bucket.grant_read(oai)

        # CloudFront distribution
        self.distribution = cloudfront.Distribution(
            self,
            "FrontendDistribution",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3Origin(
                    self.frontend_bucket,
                    origin_access_identity=oai,
                ),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                allowed_methods=cloudfront.AllowedMethods.ALLOW_GET_HEAD,
                cached_methods=cloudfront.CachedMethods.CACHE_GET_HEAD,
            ),
            default_root_object="index.html",
            error_responses=[
                cloudfront.ErrorResponse(
                    http_status=404,
                    response_http_status=200,
                    response_page_path="/index.html",
                    ttl=Duration.minutes(5),
                ),
                cloudfront.ErrorResponse(
                    http_status=403,
                    response_http_status=200,
                    response_page_path="/index.html",
                    ttl=Duration.minutes(5),
                ),
            ],
        )

        # =======================
        # OUTPUTS
        # =======================

        CfnOutput(
            self,
            "DataBucketName",
            value=self.data_bucket.bucket_name,
            description="S3 data lake bucket name",
        )

        CfnOutput(
            self,
            "HttpApiUrl",
            value=self.api.api_endpoint,
            description="HTTP API Gateway URL",
        )

        CfnOutput(
            self,
            "CloudFrontDomain",
            value=self.distribution.distribution_domain_name,
            description="CloudFront distribution domain",
        )

        CfnOutput(
            self,
            "CloudFrontDistributionId",
            value=self.distribution.distribution_id,
            description="CloudFront distribution ID for invalidations",
        )

        CfnOutput(
            self,
            "FrontendBucketName",
            value=self.frontend_bucket.bucket_name,
            description="Frontend S3 bucket name",
        )

        CfnOutput(
            self,
            "UserPoolId",
            value=self.user_pool.user_pool_id,
            description="Cognito User Pool ID",
        )

        CfnOutput(
            self,
            "UserPoolClientId",
            value=self.user_pool_client.user_pool_client_id,
            description="Cognito User Pool Client ID",
        )

        CfnOutput(
            self,
            "AthenaWorkgroup",
            value=self.athena_workgroup.name,
            description="Athena workgroup name",
        )

        CfnOutput(
            self,
            "GlueDatabase",
            value=self.glue_database.ref,
            description="Glue database name",
        )
