from io import BytesIO
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image
from rest_framework.test import APIClient


class ProfileAvatarTests(TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        media_settings = override_settings(MEDIA_ROOT=directory.name)
        media_settings.enable()
        self.addCleanup(media_settings.disable)
        self.user = get_user_model().objects.create_user(
            username="avatar-owner", full_name="Avatar Owner", email="owner@example.com"
        )
        self.other = get_user_model().objects.create_user(username="other-user")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def image(self, image_format="PNG"):
        data = BytesIO()
        Image.new("RGB", (16, 16), "blue").save(data, format=image_format)
        extension = "jpg" if image_format == "JPEG" else image_format.lower()
        return SimpleUploadedFile(
            f"avatar.{extension}", data.getvalue(), content_type=f"image/{extension}"
        )

    def form_data(self, **changes):
        return {
            "full_name": self.user.full_name,
            "student_id": self.user.student_id or "",
            "email": self.user.email,
            **changes,
        }

    def test_upload_and_replace_avatar_keeps_profile_fields_and_other_user(self):
        self.assertIsNone(self.client.get("/api/auth/me/").data["avatar"])
        names = []
        for image_format in ("PNG", "JPEG", "WEBP"):
            with self.subTest(image_format=image_format):
                response = self.client.post(
                    "/api/auth/me/",
                    self.form_data(avatar=self.image(image_format)),
                    format="multipart",
                )
                self.assertEqual(response.status_code, 200)
                self.assertTrue(
                    response.data["avatar"].startswith(
                        "http://testserver/media/avatars/"
                    )
                )
                self.user.refresh_from_db()
                self.assertEqual(self.user.full_name, "Avatar Owner")
                self.assertEqual(self.user.email, "owner@example.com")
                self.assertIsNone(self.user.student_id)
                names.append(self.user.avatar.name)
                self.assertTrue(self.user.avatar.storage.exists(self.user.avatar.name))
                with self.user.avatar.open("rb") as uploaded:
                    self.assertEqual(Image.open(uploaded).format, image_format)
                self.assertEqual(
                    self.client.get("/api/auth/me/").data["avatar"],
                    response.data["avatar"],
                )
        self.assertEqual(len(set(names)), 3)
        response = self.client.post(
            "/api/auth/me/",
            {"full_name": "Ảnh mới", "student_id": None, "email": self.user.email},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.avatar.name, names[-1])
        self.other.refresh_from_db()
        self.assertFalse(self.other.avatar)

    def test_invalid_files_do_not_replace_existing_avatar(self):
        self.client.post(
            "/api/auth/me/", self.form_data(avatar=self.image()), format="multipart"
        )
        self.user.refresh_from_db()
        original = self.user.avatar.name
        large_image = self.image()
        too_large = SimpleUploadedFile(
            "large.png",
            large_image.read() + b"0" * (5 * 1024 * 1024),
            content_type="image/png",
        )
        uploads = [
            SimpleUploadedFile("fake.png", b"not an image", content_type="image/png"),
            SimpleUploadedFile(
                "avatar.svg",
                b'<svg xmlns="http://www.w3.org/2000/svg"/>',
                content_type="image/svg+xml",
            ),
            self.image("GIF"),
            too_large,
        ]
        for upload in uploads:
            with self.subTest(file=upload.name):
                response = self.client.post(
                    "/api/auth/me/", self.form_data(avatar=upload), format="multipart"
                )
                self.assertEqual(response.status_code, 400)
                self.user.refresh_from_db()
                self.assertEqual(self.user.avatar.name, original)

    def test_avatar_upload_requires_authentication(self):
        response = APIClient().post(
            "/api/auth/me/", self.form_data(avatar=self.image()), format="multipart"
        )
        self.assertEqual(response.status_code, 401)
        self.user.refresh_from_db()
        self.assertFalse(self.user.avatar)

    def test_post_upload_can_preserve_a_new_users_empty_profile(self):
        self.user.full_name = self.user.email = ""
        self.user.save(update_fields=["full_name", "email"])
        response = self.client.post(
            "/api/auth/me/", self.form_data(avatar=self.image()), format="multipart"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["full_name"], "")
        self.assertEqual(response.data["email"], "")
        self.assertIsNone(response.data["student_id"])
