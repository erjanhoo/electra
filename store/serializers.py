from django.contrib.auth.models import User
from decimal import Decimal
from django.utils.text import slugify

from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import BillingProfile, CartItem, Category, Order, OrderItem, Product, ProductReview
from .permissions import is_admin_user


class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    is_admin = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'first_name', 'last_name', 'full_name', 'is_admin')

    def get_full_name(self, obj):
        return obj.get_full_name()

    def get_is_admin(self, obj):
        return is_admin_user(obj)


class RegisterSerializer(serializers.ModelSerializer):
    name = serializers.CharField(write_only=True)
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ('name', 'email', 'password')

    def validate_email(self, value):
        email = value.lower().strip()
        if User.objects.filter(email=email).exists():
            raise serializers.ValidationError('A user with that email already exists.')
        return email

    def create(self, validated_data):
        name = validated_data.pop('name', '').strip()
        name_parts = name.split(maxsplit=1)
        first_name = name_parts[0] if name_parts else validated_data['email'].split('@')[0]
        last_name = name_parts[1] if len(name_parts) > 1 else ''

        return User.objects.create_user(
            username=validated_data['email'],
            email=validated_data['email'],
            password=validated_data['password'],
            first_name=first_name,
            last_name=last_name,
        )


class EmailTokenObtainPairSerializer(TokenObtainPairSerializer):
    email = serializers.EmailField(required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.username_field in self.fields:
            self.fields[self.username_field].required = False

    def validate(self, attrs):
        username_key = self.username_field
        email = attrs.get('email', '').strip().lower()
        username = attrs.get(username_key)

        if not username and email:
            user = User.objects.filter(email=email).first()
            attrs[username_key] = user.username if user else email

        if not attrs.get(username_key):
            raise serializers.ValidationError({'email': 'Email is required.'})

        attrs.pop('email', None)

        return super().validate(attrs)


class AdminCategorySerializer(serializers.ModelSerializer):
    product_count = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ('id', 'name', 'slug', 'product_count', 'created_at', 'updated_at')
        read_only_fields = ('id', 'product_count', 'created_at', 'updated_at')
        extra_kwargs = {
            'slug': {'required': False, 'allow_blank': True},
        }

    def get_product_count(self, obj):
        product_count_map = self.context.get('product_count_map') or {}
        return int(product_count_map.get(obj.slug, 0))

    def validate_name(self, value):
        name = value.strip()
        if not name:
            raise serializers.ValidationError('Category name is required.')

        queryset = Category.objects.filter(name__iexact=name)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError('Category name already exists.')

        return name

    def validate_slug(self, value):
        normalized = slugify(value.strip())
        if not normalized:
            raise serializers.ValidationError('Category slug is invalid.')

        queryset = Category.objects.filter(slug=normalized)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError('Category slug already exists.')

        return normalized

    def create(self, validated_data):
        if not validated_data.get('slug'):
            base_slug = slugify(validated_data['name']) or 'category'
            slug_candidate = base_slug
            counter = 2
            while Category.objects.filter(slug=slug_candidate).exists():
                slug_candidate = f'{base_slug}-{counter}'
                counter += 1
            validated_data['slug'] = slug_candidate

        return super().create(validated_data)


class ProductCategoryLabelMixin:
    def _category_name_map(self):
        category_map = self.context.get('category_name_map')
        if category_map is not None:
            return category_map

        if not hasattr(self, '_cached_category_name_map'):
            self._cached_category_name_map = {
                category.slug: category.name
                for category in Category.objects.all().only('slug', 'name')
            }

        return self._cached_category_name_map

    def get_category_label(self, obj):
        category_map = self._category_name_map()
        return category_map.get(obj.category, obj.category.replace('-', ' ').replace('_', ' ').title())


class ProductListSerializer(ProductCategoryLabelMixin, serializers.ModelSerializer):
    category_label = serializers.SerializerMethodField()
    in_stock = serializers.BooleanField(read_only=True)
    rating = serializers.SerializerMethodField()
    review_count = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = (
            'id',
            'name',
            'slug',
            'brand',
            'category',
            'category_label',
            'short_description',
            'price',
            'compare_at_price',
            'rating',
            'review_count',
            'badge',
            'image_url',
            'is_featured',
            'in_stock',
        )

    def get_rating(self, obj):
        rating = getattr(obj, 'calculated_rating', None)
        if rating is None:
            rating = obj.rating
        return str(Decimal(str(rating)).quantize(Decimal('0.01')))

    def get_review_count(self, obj):
        review_count = getattr(obj, 'calculated_review_count', None)
        if review_count is None:
            review_count = obj.review_count
        return int(review_count)


class AdminProductSerializer(ProductCategoryLabelMixin, serializers.ModelSerializer):
    category_label = serializers.SerializerMethodField()
    in_stock = serializers.BooleanField(read_only=True)
    rating = serializers.SerializerMethodField()
    review_count = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = (
            'id',
            'name',
            'slug',
            'brand',
            'category',
            'category_label',
            'short_description',
            'description',
            'specs',
            'gallery',
            'price',
            'compare_at_price',
            'rating',
            'review_count',
            'stock',
            'in_stock',
            'image_url',
            'badge',
            'is_active',
            'is_featured',
            'released_at',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('rating', 'review_count', 'created_at', 'updated_at')

    def get_rating(self, obj):
        rating = getattr(obj, 'calculated_rating', None)
        if rating is None:
            rating = obj.rating
        return str(Decimal(str(rating)).quantize(Decimal('0.01')))

    def get_review_count(self, obj):
        review_count = getattr(obj, 'calculated_review_count', None)
        if review_count is None:
            review_count = obj.review_count
        return int(review_count)

    def validate_category(self, value):
        slug = value.strip().lower()
        if not slug:
            raise serializers.ValidationError('Category is required.')

        if not Category.objects.filter(slug=slug).exists():
            raise serializers.ValidationError('Selected category does not exist.')

        return slug


class ProductDetailSerializer(ProductListSerializer):
    class Meta(ProductListSerializer.Meta):
        fields = ProductListSerializer.Meta.fields + (
            'description',
            'specs',
            'gallery',
            'stock',
        )


class CartProductSerializer(ProductCategoryLabelMixin, serializers.ModelSerializer):
    category_label = serializers.SerializerMethodField()
    in_stock = serializers.BooleanField(read_only=True)

    class Meta:
        model = Product
        fields = (
            'id',
            'name',
            'slug',
            'brand',
            'category',
            'category_label',
            'price',
            'image_url',
            'in_stock',
            'stock',
        )


class CartItemSerializer(serializers.ModelSerializer):
    product = CartProductSerializer(read_only=True)
    line_total = serializers.SerializerMethodField()

    class Meta:
        model = CartItem
        fields = (
            'id',
            'product',
            'quantity',
            'line_total',
            'updated_at',
        )

    def get_line_total(self, obj):
        return obj.product.price * obj.quantity


class CartAddItemSerializer(serializers.Serializer):
    product_slug = serializers.SlugField()
    quantity = serializers.IntegerField(min_value=1, default=1)

    def validate_product_slug(self, value):
        slug = value.strip().lower()
        product = Product.objects.filter(slug=slug, is_active=True).first()
        if not product:
            raise serializers.ValidationError('Product not found.')
        return slug

    def validate(self, attrs):
        attrs['product'] = Product.objects.get(slug=attrs['product_slug'], is_active=True)
        return attrs


class CartUpdateItemSerializer(serializers.Serializer):
    quantity = serializers.IntegerField(min_value=1)


class ProductReviewSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()
    is_mine = serializers.SerializerMethodField()

    class Meta:
        model = ProductReview
        fields = (
            'id',
            'user_name',
            'rating',
            'title',
            'comment',
            'is_mine',
            'created_at',
            'updated_at',
        )

    def get_user_name(self, obj):
        full_name = obj.user.get_full_name().strip()
        return full_name or obj.user.username or obj.user.email.split('@')[0]

    def get_is_mine(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False
        return request.user.id == obj.user_id


class ProductReviewUpsertSerializer(serializers.Serializer):
    rating = serializers.IntegerField(min_value=1, max_value=5)
    title = serializers.CharField(required=False, allow_blank=True, max_length=140)
    comment = serializers.CharField(required=False, allow_blank=True)


class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = (
            'id',
            'product_name',
            'product_brand',
            'product_slug',
            'image_url',
            'unit_price',
            'quantity',
            'line_total',
        )


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = (
            'id',
            'order_number',
            'status',
            'delivery_method',
            'item_count',
            'subtotal',
            'tax_amount',
            'shipping_amount',
            'total_amount',
            'payment_brand',
            'payment_last4',
            'used_wallet',
            'placed_at',
            'items',
        )


class AdminOrderSerializer(OrderSerializer):
    user_id = serializers.IntegerField(source='user.id', read_only=True)
    user_email = serializers.EmailField(source='user.email', read_only=True)
    user_name = serializers.SerializerMethodField()

    class Meta(OrderSerializer.Meta):
        fields = OrderSerializer.Meta.fields + (
            'user_id',
            'user_email',
            'user_name',
        )

    def get_user_name(self, obj):
        full_name = obj.user.get_full_name().strip()
        return full_name or obj.user.username or obj.user.email


class BillingProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = BillingProfile
        fields = (
            'is_card_linked',
            'card_holder_name',
            'card_brand',
            'card_last4',
            'wallet_balance',
            'total_spent',
        )


class LinkCardSerializer(serializers.Serializer):
    card_holder_name = serializers.CharField(max_length=120)
    card_number = serializers.CharField(write_only=True)
    card_brand = serializers.CharField(max_length=30, required=False, allow_blank=True)
    expiry = serializers.CharField(max_length=7)
    cvv = serializers.CharField(max_length=4, write_only=True)

    def validate_card_number(self, value):
        digits = ''.join(ch for ch in value if ch.isdigit())
        if len(digits) < 12 or len(digits) > 19:
            raise serializers.ValidationError('Card number looks invalid.')
        return digits

    def validate_expiry(self, value):
        normalized = value.strip()
        if '/' not in normalized or len(normalized) < 4:
            raise serializers.ValidationError('Expiry must look like MM/YY.')
        return normalized

    def validate_cvv(self, value):
        digits = ''.join(ch for ch in value if ch.isdigit())
        if len(digits) not in (3, 4):
            raise serializers.ValidationError('CVV must be 3 or 4 digits.')
        return digits

    def save(self, profile: BillingProfile):
        card_number = self.validated_data['card_number']
        requested_brand = self.validated_data.get('card_brand', '').strip()

        profile.card_holder_name = self.validated_data['card_holder_name'].strip()
        profile.card_last4 = card_number[-4:]
        profile.card_brand = requested_brand or self._detect_brand(card_number)
        profile.is_card_linked = True
        profile.save(update_fields=['card_holder_name', 'card_last4', 'card_brand', 'is_card_linked', 'updated_at'])
        return profile

    @staticmethod
    def _detect_brand(card_number: str):
        if card_number.startswith('4'):
            return 'Visa'
        if card_number.startswith(('51', '52', '53', '54', '55')):
            return 'Mastercard'
        if card_number.startswith(('34', '37')):
            return 'American Express'
        if card_number.startswith('6'):
            return 'Discover'
        return 'Card'


class TopUpSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal('1.00'))


class CheckoutSimulationSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal('0.01'))
    item_count = serializers.IntegerField(min_value=1)
    delivery_method = serializers.ChoiceField(choices=['standard', 'express'])
