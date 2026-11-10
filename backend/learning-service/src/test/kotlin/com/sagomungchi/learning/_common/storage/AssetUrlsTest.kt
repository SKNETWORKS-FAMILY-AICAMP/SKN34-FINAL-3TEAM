package com.sagomungchi.learning._common.storage

import org.junit.jupiter.api.Test
import org.junit.jupiter.api.assertThrows
import software.amazon.awssdk.auth.credentials.AwsBasicCredentials
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider
import java.time.Duration
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue

/** 저장 값 → URL (#438): S3 키는 presigned, 주소는 그대로, 버킷 설정이 없으면 null */
class AssetUrlsTest {
    private val credentials = StaticCredentialsProvider.create(AwsBasicCredentials.create("test-access", "test-secret"))

    @Test
    fun `S3 키는 공개 주소(경로 방식)로 서명한 단기 URL`() {
        AssetUrls(AssetProperties(bucket = "theme-bucket", publicEndpoint = "http://127.0.0.1:19000"), credentials).use { urls ->
            val url = urls.url("theme-drafts/run-1/INTRO.png")!!
            assertTrue(url.startsWith("http://127.0.0.1:19000/theme-bucket/theme-drafts/run-1/INTRO.png?"), url)
            assertTrue("X-Amz-Expires=3600" in url, url)
            assertTrue("X-Amz-Signature=" in url, url)
        }
    }

    @Test
    fun `공개 주소가 없으면 AWS S3 주소로 서명`() {
        AssetUrls(AssetProperties(bucket = "theme-bucket", urlTtl = Duration.ofMinutes(10)), credentials).use { urls ->
            val url = urls.url("theme-drafts/run-1/MON.mp4")!!
            assertTrue(url.startsWith("https://theme-bucket.s3.ap-northeast-2.amazonaws.com/theme-drafts/run-1/MON.mp4?"), url)
            assertTrue("X-Amz-Expires=600" in url, url)
        }
    }

    @Test
    fun `사람이 넣은 주소는 그대로, 빈 값은 null, 버킷이 없으면 키는 null`() {
        AssetUrls(AssetProperties(), credentials).use { urls ->
            assertEquals("https://cdn.example/scene.png", urls.url("https://cdn.example/scene.png"))
            assertEquals("/scenes/demo.png", urls.url("/scenes/demo.png"))
            assertNull(urls.url(null))
            assertNull(urls.url(" "))
            assertNull(urls.url("theme-drafts/run-1/INTRO.png"))
        }
    }

    @Test
    fun `유효기간은 1초~1시간`() {
        assertThrows<IllegalArgumentException> { AssetProperties(urlTtl = Duration.ofHours(2)) }
        assertThrows<IllegalArgumentException> { AssetProperties(urlTtl = Duration.ZERO) }
    }
}
