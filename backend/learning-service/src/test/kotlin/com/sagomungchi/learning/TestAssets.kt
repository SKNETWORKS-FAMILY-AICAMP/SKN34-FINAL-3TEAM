package com.sagomungchi.learning

import com.sagomungchi.learning._common.storage.AssetProperties
import com.sagomungchi.learning._common.storage.AssetUrls
import software.amazon.awssdk.auth.credentials.AwsBasicCredentials
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider

/** 테스트용 presigned URL (#438): 버킷·공개 주소가 있어 S3 키가 http://assets.test/theme-test/{키}?… 로 바뀜 */
object TestAssets {
    const val BASE = "http://assets.test/theme-test/"
    val urls = AssetUrls(
        AssetProperties(bucket = "theme-test", publicEndpoint = "http://assets.test"),
        StaticCredentialsProvider.create(AwsBasicCredentials.create("test-access", "test-secret")),
    )
}
