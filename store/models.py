from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MaxValueValidator, MinValueValidator
from django.utils import timezone
from django.utils.text import slugify


class Category(models.Model):
	name = models.CharField(max_length=80, unique=True)
	slug = models.SlugField(max_length=64, unique=True, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ['name']

	def __str__(self):
		return self.name

	def save(self, *args, **kwargs):
		if not self.slug:
			base_slug = slugify(self.name) or 'category'
			slug = base_slug
			counter = 2

			while Category.objects.filter(slug=slug).exclude(pk=self.pk).exists():
				slug = f'{base_slug}-{counter}'
				counter += 1

			self.slug = slug

		super().save(*args, **kwargs)


class Product(models.Model):
	name = models.CharField(max_length=180)
	slug = models.SlugField(max_length=200, unique=True, blank=True)
	brand = models.CharField(max_length=80)
	category = models.CharField(max_length=64, db_index=True)

	short_description = models.TextField()
	description = models.TextField()
	specs = models.JSONField(default=dict, blank=True)

	price = models.DecimalField(max_digits=10, decimal_places=2)
	compare_at_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
	rating = models.DecimalField(max_digits=3, decimal_places=2, default=0)
	review_count = models.PositiveIntegerField(default=0)
	stock = models.PositiveIntegerField(default=0)

	image_url = models.URLField(max_length=500)
	gallery = models.JSONField(default=list, blank=True)
	badge = models.CharField(max_length=80, blank=True)

	is_active = models.BooleanField(default=True)
	is_featured = models.BooleanField(default=False)
	released_at = models.DateField(null=True, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ['-is_featured', '-released_at', 'name']

	def __str__(self):
		return f'{self.brand} {self.name}'

	@property
	def in_stock(self):
		return self.stock > 0

	def save(self, *args, **kwargs):
		if not self.slug:
			base_slug = slugify(f'{self.brand}-{self.name}') or 'product'
			slug = base_slug
			counter = 2

			while Product.objects.filter(slug=slug).exclude(pk=self.pk).exists():
				slug = f'{base_slug}-{counter}'
				counter += 1

			self.slug = slug

		super().save(*args, **kwargs)


class BillingProfile(models.Model):
	user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='billing_profile')
	is_card_linked = models.BooleanField(default=False)
	card_holder_name = models.CharField(max_length=120, blank=True)
	card_brand = models.CharField(max_length=30, blank=True)
	card_last4 = models.CharField(max_length=4, blank=True)
	wallet_balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)
	total_spent = models.DecimalField(max_digits=12, decimal_places=2, default=0)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ['-updated_at']

	def __str__(self):
		if self.is_card_linked and self.card_last4:
			return f'{self.user.email} •••• {self.card_last4}'
		return f'{self.user.email} (card not linked)'


class CartItem(models.Model):
	user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='cart_items')
	product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='cart_items')
	quantity = models.PositiveIntegerField(default=1)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ['-updated_at']
		constraints = [
			models.UniqueConstraint(fields=['user', 'product'], name='unique_user_product_cart_item'),
		]

	def __str__(self):
		return f'{self.user.email} · {self.product.name} x{self.quantity}'


class Order(models.Model):
	DELIVERY_CHOICES = [
		('standard', 'Standard Shipping'),
		('express', 'Express Delivery'),
	]

	STATUS_CHOICES = [
		('completed', 'Completed'),
		('processing', 'Processing'),
		('cancelled', 'Cancelled'),
	]

	user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='orders')
	order_number = models.CharField(max_length=40, unique=True, db_index=True)
	status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='completed')
	delivery_method = models.CharField(max_length=20, choices=DELIVERY_CHOICES, default='standard')
	item_count = models.PositiveIntegerField(default=0)

	subtotal = models.DecimalField(max_digits=10, decimal_places=2)
	tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
	shipping_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
	total_amount = models.DecimalField(max_digits=10, decimal_places=2)

	payment_brand = models.CharField(max_length=30, blank=True)
	payment_last4 = models.CharField(max_length=4, blank=True)
	used_wallet = models.BooleanField(default=False)

	placed_at = models.DateTimeField(default=timezone.now)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ['-placed_at']

	def __str__(self):
		return f'{self.order_number} ({self.user.email})'


class OrderItem(models.Model):
	order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
	product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True, related_name='order_items')
	product_name = models.CharField(max_length=180)
	product_brand = models.CharField(max_length=80, blank=True)
	product_slug = models.CharField(max_length=200, blank=True)
	image_url = models.URLField(max_length=500, blank=True)
	unit_price = models.DecimalField(max_digits=10, decimal_places=2)
	quantity = models.PositiveIntegerField(default=1)
	line_total = models.DecimalField(max_digits=10, decimal_places=2)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ['id']

	def __str__(self):
		return f'{self.order.order_number} · {self.product_name} x{self.quantity}'


class ProductReview(models.Model):
	user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='product_reviews')
	product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='reviews')
	rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
	title = models.CharField(max_length=140, blank=True)
	comment = models.TextField(blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ['-updated_at']
		constraints = [
			models.UniqueConstraint(fields=['user', 'product'], name='unique_user_product_review'),
		]

	def __str__(self):
		return f'{self.user.email} → {self.product.name} ({self.rating}/5)'
