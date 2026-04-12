from django.contrib.auth.models import User
from decimal import Decimal, InvalidOperation
from random import randint

from django.db import transaction
from django.db.models import Avg, Count, DecimalField, IntegerField, Max, Min, Sum, Value
from django.db.models import Q
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.generics import CreateAPIView, ListAPIView, ListCreateAPIView, RetrieveAPIView, RetrieveUpdateDestroyAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import BillingProfile, CartItem, Category, Order, OrderItem, Product, ProductReview
from .permissions import IsAdminAccount
from .serializers import (
    AdminCategorySerializer,
    AdminOrderSerializer,
    AdminProductSerializer,
    BillingProfileSerializer,
    CartAddItemSerializer,
    CartItemSerializer,
    CartUpdateItemSerializer,
    CheckoutSimulationSerializer,
    EmailTokenObtainPairSerializer,
    LinkCardSerializer,
    OrderSerializer,
    ProductDetailSerializer,
    ProductListSerializer,
    ProductReviewSerializer,
    ProductReviewUpsertSerializer,
    RegisterSerializer,
    TopUpSerializer,
    UserSerializer,
)


class EmailTokenObtainPairView(TokenObtainPairView):
    serializer_class = EmailTokenObtainPairSerializer


class RegisterAPIView(CreateAPIView):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        refresh = RefreshToken.for_user(user)

        data = {
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'user': UserSerializer(user).data,
        }

        headers = self.get_success_headers(serializer.data)
        return Response(data, status=status.HTTP_201_CREATED, headers=headers)


class UserDetailAPIView(RetrieveAPIView):
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user


def with_review_metrics(queryset):
    return queryset.annotate(
        calculated_rating=Coalesce(
            Avg('reviews__rating'),
            Value(Decimal('0.00')),
            output_field=DecimalField(max_digits=3, decimal_places=2),
        ),
        calculated_review_count=Coalesce(
            Count('reviews', distinct=True),
            Value(0),
            output_field=IntegerField(),
        ),
    )


def user_has_purchased_product(user: User, product: Product):
    return OrderItem.objects.filter(
        order__user=user,
        order__status='completed',
    ).filter(
        Q(product=product) | Q(product_slug=product.slug)
    ).exists()


def get_product_review_metrics(product: Product):
    metrics = ProductReview.objects.filter(product=product).aggregate(avg_rating=Avg('rating'), total=Count('id'))
    avg_rating = Decimal(str(metrics['avg_rating'] or 0)).quantize(Decimal('0.01'))
    review_count = metrics['total'] or 0
    return avg_rating, review_count


class ProductListAPIView(ListAPIView):
    serializer_class = ProductListSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        queryset = with_review_metrics(Product.objects.filter(is_active=True))

        search = self.request.query_params.get('search')
        categories = self._get_list_param('category')
        brands = self._get_list_param('brand')
        min_price = self._parse_decimal(self.request.query_params.get('min_price'))
        max_price = self._parse_decimal(self.request.query_params.get('max_price'))
        min_rating = self._parse_decimal(self.request.query_params.get('min_rating'))
        ordering = self.request.query_params.get('ordering', 'featured')

        if search:
            queryset = queryset.filter(
                Q(name__icontains=search)
                | Q(brand__icontains=search)
                | Q(short_description__icontains=search)
            )

        if categories:
            queryset = queryset.filter(category__in=categories)

        if brands:
            queryset = queryset.filter(brand__in=brands)

        if min_price is not None:
            queryset = queryset.filter(price__gte=min_price)

        if max_price is not None:
            queryset = queryset.filter(price__lte=max_price)

        if min_rating is not None:
            queryset = queryset.filter(calculated_rating__gte=min_rating)

        if ordering == 'newest':
            queryset = queryset.order_by('-released_at', '-created_at', '-calculated_rating')
        elif ordering == 'price_asc':
            queryset = queryset.order_by('price', '-calculated_rating')
        elif ordering == 'price_desc':
            queryset = queryset.order_by('-price', '-calculated_rating')
        elif ordering == 'rating':
            queryset = queryset.order_by('-calculated_rating', '-calculated_review_count')
        else:
            queryset = queryset.order_by('-is_featured', '-calculated_rating', '-calculated_review_count')

        return queryset

    def _get_list_param(self, key):
        values = [value.strip() for value in self.request.query_params.getlist(key) if value and value.strip()]

        if values:
            return values

        fallback = self.request.query_params.get(key)
        if not fallback:
            return []

        return [value.strip() for value in fallback.split(',') if value and value.strip()]

    @staticmethod
    def _parse_decimal(value):
        if value in (None, ''):
            return None
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError):
            return None


class ProductDetailAPIView(RetrieveAPIView):
    serializer_class = ProductDetailSerializer
    permission_classes = [AllowAny]
    lookup_field = 'slug'

    def get_queryset(self):
        return with_review_metrics(Product.objects.filter(is_active=True))


class ProductReviewListCreateAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, slug):
        product = get_object_or_404(Product, slug=slug, is_active=True)
        reviews = ProductReview.objects.filter(product=product).select_related('user')
        rating, review_count = get_product_review_metrics(product)
        can_review = request.user.is_authenticated and user_has_purchased_product(request.user, product)

        return Response(
            {
                'product_slug': product.slug,
                'rating': rating,
                'review_count': review_count,
                'can_review': can_review,
                'rating_distribution': get_product_rating_distribution(product),
                'results': ProductReviewSerializer(reviews, many=True, context={'request': request}).data,
            }
        )

    def post(self, request, slug):
        if not request.user.is_authenticated:
            return Response({'detail': 'Authentication credentials were not provided.'}, status=status.HTTP_401_UNAUTHORIZED)

        product = get_object_or_404(Product, slug=slug, is_active=True)

        if not user_has_purchased_product(request.user, product):
            return Response(
                {'detail': 'You can review this product only after purchasing it.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = ProductReviewUpsertSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        defaults = {
            'rating': serializer.validated_data['rating'],
            'title': serializer.validated_data.get('title', '').strip(),
            'comment': serializer.validated_data.get('comment', '').strip(),
        }

        review, created = ProductReview.objects.update_or_create(
            user=request.user,
            product=product,
            defaults=defaults,
        )

        refresh_product_review_metrics(product)

        return Response(
            {
                'message': 'Review created.' if created else 'Review updated.',
                'review': ProductReviewSerializer(review, context={'request': request}).data,
                'rating': product.rating,
                'review_count': product.review_count,
                'rating_distribution': get_product_rating_distribution(product),
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    def delete(self, request, slug):
        if not request.user.is_authenticated:
            return Response({'detail': 'Authentication credentials were not provided.'}, status=status.HTTP_401_UNAUTHORIZED)

        product = get_object_or_404(Product, slug=slug, is_active=True)
        deleted_count, _ = ProductReview.objects.filter(product=product, user=request.user).delete()

        if deleted_count == 0:
            return Response({'detail': 'You have no review for this product.'}, status=status.HTTP_404_NOT_FOUND)

        refresh_product_review_metrics(product)

        return Response(
            {
                'message': 'Review deleted.',
                'rating': product.rating,
                'review_count': product.review_count,
                'rating_distribution': get_product_rating_distribution(product),
            }
        )


class OrderHistoryAPIView(ListAPIView):
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Order.objects.filter(user=self.request.user).prefetch_related('items')


class OrderDetailAPIView(RetrieveAPIView):
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = 'order_number'

    def get_queryset(self):
        return Order.objects.filter(user=self.request.user).prefetch_related('items')


class AdminDashboardAPIView(APIView):
    permission_classes = [IsAdminAccount]

    def get(self, request):
        today = timezone.now().date()
        products = Product.objects.all()
        orders = Order.objects.all()

        return Response(
            {
                'products_total': products.count(),
                'products_active': products.filter(is_active=True).count(),
                'products_inactive': products.filter(is_active=False).count(),
                'orders_total': orders.count(),
                'orders_today': orders.filter(placed_at__date=today).count(),
                'users_total': User.objects.count(),
                'revenue_total': orders.aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00'),
            }
        )


class AdminProductListCreateAPIView(ListCreateAPIView):
    serializer_class = AdminProductSerializer
    permission_classes = [IsAdminAccount]

    def get_queryset(self):
        queryset = with_review_metrics(Product.objects.all()).order_by('-updated_at', '-id')

        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search)
                | Q(brand__icontains=search)
                | Q(short_description__icontains=search)
            )

        return queryset


class AdminProductDetailAPIView(RetrieveUpdateDestroyAPIView):
    serializer_class = AdminProductSerializer
    permission_classes = [IsAdminAccount]
    queryset = with_review_metrics(Product.objects.all())

    def delete(self, request, *args, **kwargs):
        product = self.get_object()

        if not product.is_active:
            return Response({'message': 'Product already deactivated.'}, status=status.HTTP_200_OK)

        product.is_active = False
        product.save(update_fields=['is_active', 'updated_at'])

        return Response({'message': 'Product deactivated.', 'id': product.id, 'is_active': product.is_active})


class AdminCategoryListCreateAPIView(ListCreateAPIView):
    serializer_class = AdminCategorySerializer
    permission_classes = [IsAdminAccount]
    queryset = Category.objects.all().order_by('name', 'id')

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['product_count_map'] = {
            item['category']: item['count']
            for item in Product.objects.values('category').annotate(count=Count('id'))
        }
        return context


class AdminCategoryDetailAPIView(RetrieveUpdateDestroyAPIView):
    serializer_class = AdminCategorySerializer
    permission_classes = [IsAdminAccount]
    queryset = Category.objects.all()

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['product_count_map'] = {
            item['category']: item['count']
            for item in Product.objects.values('category').annotate(count=Count('id'))
        }
        return context

    def perform_update(self, serializer):
        old_slug = serializer.instance.slug

        with transaction.atomic():
            category = serializer.save()
            if old_slug != category.slug:
                Product.objects.filter(category=old_slug).update(category=category.slug)

    def destroy(self, request, *args, **kwargs):
        category = self.get_object()
        product_count = Product.objects.filter(category=category.slug).count()

        if product_count > 0:
            return Response(
                {'detail': f'Cannot delete category used by {product_count} products.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        slug = category.slug
        category.delete()
        return Response({'message': f'Category {slug} deleted.'}, status=status.HTTP_200_OK)


class AdminOrderListAPIView(ListAPIView):
    serializer_class = AdminOrderSerializer
    permission_classes = [IsAdminAccount]

    def get_queryset(self):
        return Order.objects.all().select_related('user').prefetch_related('items')


class ProductFiltersAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        active_products = Product.objects.filter(is_active=True)
        categories = active_products.values('category').annotate(count=Count('id')).order_by('category')
        category_counts = {item['category']: item['count'] for item in categories}

        category_payload = []
        for category in Category.objects.all().order_by('name', 'id'):
            count = category_counts.pop(category.slug, 0)
            if count <= 0:
                continue
            category_payload.append(
                {
                    'value': category.slug,
                    'label': category.name,
                    'count': count,
                }
            )

        for slug, count in sorted(category_counts.items()):
            if count <= 0:
                continue
            category_payload.append(
                {
                    'value': slug,
                    'label': slug.replace('-', ' ').replace('_', ' ').title(),
                    'count': count,
                }
            )

        brands = active_products.values('brand').annotate(count=Count('id')).order_by('brand')
        price_stats = active_products.aggregate(min_price=Min('price'), max_price=Max('price'))

        return Response(
            {
                'categories': category_payload,
                'brands': [
                    {
                        'value': item['brand'],
                        'label': item['brand'],
                        'count': item['count'],
                    }
                    for item in brands
                ],
                'price_range': {
                    'min': 0,
                    'max': price_stats['max_price'] or 0,
                },
            }
        )


def get_cart_queryset(user):
    return CartItem.objects.filter(user=user).select_related('product')


def get_cart_payload(user):
    cart_items = get_cart_queryset(user)

    subtotal = sum(
        (item.product.price * item.quantity for item in cart_items),
        Decimal('0.00'),
    )
    item_count = sum(item.quantity for item in cart_items)

    return {
        'items': CartItemSerializer(cart_items, many=True).data,
        'item_count': item_count,
        'subtotal': subtotal,
    }


def refresh_product_review_metrics(product: Product):
    rating, review_count = get_product_review_metrics(product)

    product.rating = rating
    product.review_count = review_count
    product.save(update_fields=['rating', 'review_count', 'updated_at'])


def get_product_rating_distribution(product: Product):
    grouped = ProductReview.objects.filter(product=product).values('rating').annotate(count=Count('id'))
    counts = {item['rating']: item['count'] for item in grouped}

    return [
        {
            'rating': rating,
            'count': counts.get(rating, 0),
        }
        for rating in range(5, 0, -1)
    ]


def build_order_number(user_id: int):
    while True:
        candidate = f"EL-{timezone.now():%y%m%d}-{user_id:04d}-{randint(1000, 9999)}"
        if not Order.objects.filter(order_number=candidate).exists():
            return candidate


class CartAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(get_cart_payload(request.user))

    def post(self, request):
        serializer = CartAddItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        product = serializer.validated_data['product']
        quantity = serializer.validated_data['quantity']

        if product.stock < 1:
            return Response(
                {'detail': f'{product.name} is currently out of stock.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if quantity > product.stock:
            return Response(
                {'detail': f'Only {product.stock} items are available for {product.name}.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cart_item, created = CartItem.objects.get_or_create(
            user=request.user,
            product=product,
            defaults={'quantity': quantity},
        )

        target_quantity = quantity if created else cart_item.quantity + quantity

        if target_quantity > product.stock:
            return Response(
                {'detail': f'Only {product.stock} items are available for {product.name}.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not created:
            cart_item.quantity = target_quantity
            cart_item.save(update_fields=['quantity', 'updated_at'])

        return Response(
            get_cart_payload(request.user),
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    def delete(self, request):
        CartItem.objects.filter(user=request.user).delete()
        return Response(get_cart_payload(request.user))


class CartItemAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, item_id):
        cart_item = get_object_or_404(CartItem.objects.select_related('product'), id=item_id, user=request.user)

        serializer = CartUpdateItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        quantity = serializer.validated_data['quantity']
        if quantity > cart_item.product.stock:
            return Response(
                {'detail': f'Only {cart_item.product.stock} items are available for {cart_item.product.name}.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cart_item.quantity = quantity
        cart_item.save(update_fields=['quantity', 'updated_at'])

        return Response(get_cart_payload(request.user))

    def delete(self, request, item_id):
        cart_item = get_object_or_404(CartItem, id=item_id, user=request.user)
        cart_item.delete()
        return Response(get_cart_payload(request.user))


def get_or_create_billing_profile(user):
    profile, _ = BillingProfile.objects.get_or_create(user=user)
    return profile


class BillingProfileAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        profile = get_or_create_billing_profile(request.user)
        return Response(BillingProfileSerializer(profile).data)

    def put(self, request):
        profile = get_or_create_billing_profile(request.user)

        serializer = LinkCardSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(profile=profile)

        return Response(BillingProfileSerializer(profile).data)


class BillingTopUpAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        profile = get_or_create_billing_profile(request.user)

        if not profile.is_card_linked:
            return Response({'detail': 'Link a card before topping up.'}, status=status.HTTP_400_BAD_REQUEST)

        serializer = TopUpSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        amount = serializer.validated_data['amount']
        profile.wallet_balance = profile.wallet_balance + amount
        profile.save(update_fields=['wallet_balance', 'updated_at'])

        return Response(
            {
                'message': 'Top-up successful.',
                'wallet_balance': profile.wallet_balance,
            }
        )


class CheckoutSimulationAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        profile = get_or_create_billing_profile(request.user)

        if not profile.is_card_linked:
            return Response({'detail': 'You need to link a card before checkout.'}, status=status.HTTP_400_BAD_REQUEST)

        serializer = CheckoutSimulationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        amount = serializer.validated_data['amount']
        delivery_method = serializer.validated_data['delivery_method']
        cart_items = list(get_cart_queryset(request.user))

        if not cart_items:
            return Response({'detail': 'Your cart is empty.'}, status=status.HTTP_400_BAD_REQUEST)

        for item in cart_items:
            if not item.product.is_active:
                return Response(
                    {'detail': f'{item.product.name} is no longer available.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if not item.product.in_stock:
                return Response(
                    {'detail': f'{item.product.name} is out of stock.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if item.quantity > item.product.stock:
                return Response(
                    {'detail': f'Only {item.product.stock} items are available for {item.product.name}.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        subtotal = sum((item.product.price * item.quantity for item in cart_items), Decimal('0.00')).quantize(Decimal('0.01'))
        shipping_amount = Decimal('25.00') if delivery_method == 'express' else Decimal('0.00')
        tax_amount = (subtotal * Decimal('0.08')).quantize(Decimal('0.01'))
        expected_total = (subtotal + shipping_amount + tax_amount).quantize(Decimal('0.01'))

        if (amount - expected_total).copy_abs() > Decimal('0.01'):
            amount = expected_total
        else:
            amount = amount.quantize(Decimal('0.01'))

        item_count = sum(item.quantity for item in cart_items)

        used_wallet = False

        if profile.wallet_balance >= amount:
            profile.wallet_balance = profile.wallet_balance - amount
            used_wallet = True

        with transaction.atomic():
            profile.total_spent = profile.total_spent + amount
            profile.save(update_fields=['wallet_balance', 'total_spent', 'updated_at'])

            order = Order.objects.create(
                user=request.user,
                order_number=build_order_number(request.user.id),
                status='completed',
                delivery_method=delivery_method,
                item_count=item_count,
                subtotal=subtotal,
                tax_amount=tax_amount,
                shipping_amount=shipping_amount,
                total_amount=amount,
                payment_brand=profile.card_brand,
                payment_last4=profile.card_last4,
                used_wallet=used_wallet,
            )

            OrderItem.objects.bulk_create(
                [
                    OrderItem(
                        order=order,
                        product=item.product,
                        product_name=item.product.name,
                        product_brand=item.product.brand,
                        product_slug=item.product.slug,
                        image_url=item.product.image_url,
                        unit_price=item.product.price,
                        quantity=item.quantity,
                        line_total=(item.product.price * item.quantity).quantize(Decimal('0.01')),
                    )
                    for item in cart_items
                ]
            )

            CartItem.objects.filter(user=request.user).delete()

        return Response(
            {
                'message': 'Checkout simulated successfully and order saved.',
                'order_number': order.order_number,
                'order_id': order.id,
                'item_count': item_count,
                'charged_amount': amount,
                'used_wallet': used_wallet,
                'wallet_balance': profile.wallet_balance,
                'card_last4': profile.card_last4,
                'card_brand': profile.card_brand,
            },
            status=status.HTTP_201_CREATED,
        )
