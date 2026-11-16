package com.sagomungchi.learning._common.storage

import org.springframework.boot.context.properties.ConfigurationProperties
import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration
import software.amazon.awssdk.auth.credentials.AwsCredentialsProvider
import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider
import software.amazon.awssdk.regions.Region
import software.amazon.awssdk.services.s3.S3Configuration
import software.amazon.awssdk.services.s3.presigner.S3Presigner
import java.net.URI
import java.time.Duration

/**
 * 테마 그림·영상 S3 설정 (`app.assets`, #438). bucket이 비면 S3 키를 URL로 바꾸지 않는다(null).
 * publicEndpoint는 로컬 MinIO처럼 브라우저가 여는 주소로 서명할 때만(경로 방식). urlTtl은 1초~1시간(report 다운로드와 같은 상한)
 */
@ConfigurationProperties("app.assets")
data class AssetProperties(
    val bucket: String = "",
    val region: String = "ap-northeast-2",
    val publicEndpoint: String = "",
    val urlTtl: Duration = Duration.ofHours(1),
) {
    init {
        require(urlTtl >= Duration.ofSeconds(1) && urlTtl <= Duration.ofHours(1)) { "app.assets.url-ttl은 1초~1시간: $urlTtl" }
    }
}

/**
 * 저장 값 → 브라우저가 여는 URL (class-diagram 4.4 AssetUrls, ERD 4.2.1).
 * ai가 올린 S3 키(`theme-drafts/{실행 ID}/{장면}`)만 단기 presigned GET URL로 바꾸고, 그 밖의 값(사람이 넣은 주소·경로)은 지금처럼 그대로.
 * 관리자 화면은 장면 칸을 자유 글로 받아 기존 값의 형식을 알 수 없으므로 접두어로만 구분한다.
 * 서명은 로컬 계산이라 S3를 부르지 않는다. 응답마다 새로 서명하므로 주소가 바뀌고, 임시 자격 증명이면 그 만료 때 URL도 만료될 수 있다
 */
class AssetUrls(
    private val properties: AssetProperties,
    credentials: AwsCredentialsProvider,
) : AutoCloseable {
    private val presigner: S3Presigner? = properties.bucket.takeIf { it.isNotBlank() }?.let {
        S3Presigner.builder()
            .region(Region.of(properties.region))
            .credentialsProvider(credentials)
            .apply {
                if (properties.publicEndpoint.isNotBlank()) {
                    endpointOverride(URI.create(properties.publicEndpoint))
                    serviceConfiguration(S3Configuration.builder().pathStyleAccessEnabled(true).build())
                }
            }
            .build()
    }

    /** 빈 값은 null, ai 키(`theme-drafts/…`)는 presigned URL(버킷 설정이 없으면 null), 그 밖은 그대로 */
    fun url(stored: String?): String? = when {
        stored.isNullOrBlank() -> null
        !stored.startsWith(KEY_PREFIX) -> stored
        else -> presigner?.presignGetObject { request ->
            request.signatureDuration(properties.urlTtl).getObjectRequest { it.bucket(properties.bucket).key(stored) }
        }?.url()?.toString()
    }

    override fun close() {
        presigner?.close()
    }

    companion object {
        /** ai가 테마 초안 그림·영상을 올리는 키 접두어 (api-spec 4.2) */
        const val KEY_PREFIX = "theme-drafts/"
    }
}

@Configuration(proxyBeanMethods = false)
class AssetConfig {
    @Bean(destroyMethod = "close")
    fun assetUrls(properties: AssetProperties): AssetUrls = AssetUrls(properties, DefaultCredentialsProvider.builder().build())
}
